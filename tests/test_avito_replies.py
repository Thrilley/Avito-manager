import os
import unittest
from unittest.mock import patch, Mock
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User, SourceAccount, AvitoReply
from app.integrations.gpt_replies import OpenAIReplies, Draft, GenerationUnavailable
from app.integrations.avito_messenger import AvitoMessenger, MessengerUnavailable
from tests import test_catalog

class AvitoTests(unittest.TestCase):
    tearDown = test_catalog.CatalogTests.tearDown

    def setUp(self):
        test_catalog.CatalogTests.setUp(self)
        with Session(self.engine) as db:
            owner = db.scalar(select(User).where(User.username == 'owner'))
            source = SourceAccount(owner_id=owner.id, platform='avito', account_id='synthetic')
            db.add(source)
            db.commit()
            self.source = source.id
        self.event = dict(chat_id='chat-1', message_id='msg-1', direction='in', text='Здравствуйте')
        self.message = self.ingest().json()
        self.chat = self.message['chat_id']
        self.path = f"/api/v1/avito/messages/{self.message['id']}/draft"

    def ingest(self, **changes):
        return self.client.post(f'/api/v1/avito/sources/{self.source}/events',
                                json=dict(self.event, **changes))

    def enable(self):
        return self.client.patch(f'/api/v1/avito/chats/{self.chat}',
                                 json=dict(enabled=True, human_required=False))

    def test_disabled_and_deduplicated(self):
        self.assertEqual(self.ingest().json(), self.message)
        self.assertEqual(self.ingest(text='Changed').status_code, 409)
        with patch.object(OpenAIReplies, 'generate') as generator:
            self.assertEqual(self.client.post(self.path).status_code, 409)
            generator.assert_not_called()
        response = self.client.get(f'/api/v1/avito/chats/{self.chat}/messages')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(len(response.json()), 1)

    def test_draft_once_and_unsent_drafts_not_in_history(self):
        self.enable()
        with patch.object(OpenAIReplies, 'generate', return_value=Draft(reply='Здравствуйте!', human_required=False)) as g:
            first = self.client.post(self.path).json()
            self.assertEqual(first['status'], 'draft')
            self.assertEqual(self.client.post(self.path).json(), first)
            g.assert_called_once()
            second = self.ingest(message_id='msg-2', text='Спасибо').json()
            self.client.post(f"/api/v1/avito/messages/{second['id']}/draft")
            self.assertEqual([r['content'] for r in g.call_args.args[0]], ['Здравствуйте', 'Спасибо'])

    def test_operator_request_without_gpt_and_queue(self):
        with patch.object(OpenAIReplies, 'generate') as g:
            row = self.ingest(message_id='operator', text='Соедините с оператором').json()
            response = self.client.post(f"/api/v1/avito/messages/{row['id']}/draft")
            self.assertEqual(response.json()['status'], 'human_required')
            g.assert_not_called()
        queue = self.client.get('/api/v1/avito/chats?human_required=true').json()
        self.assertEqual([c['id'] for c in queue], [self.chat])
        self.assertFalse(queue[0]['enabled'])
        self.assertEqual(self.ingest(message_id='operator', text='Соедините с оператором').json(), row)

    def test_handoff_and_owner_message_pause(self):
        self.enable()
        with patch.object(OpenAIReplies, 'generate', return_value=Draft(reply='Уточню у продавца.', human_required=True)):
            self.assertEqual(self.client.post(self.path).json()['status'], 'human_required')
        chat = self.client.get('/api/v1/avito/chats').json()[0]
        self.assertTrue(chat['human_required'])
        self.assertFalse(chat['enabled'])
        self.enable()
        self.ingest(message_id='seller-1', direction='out', text='Отвечаю сам')
        self.assertFalse(self.client.get('/api/v1/avito/chats').json()[0]['enabled'])

    def test_failure_is_sanitized_and_not_retried(self):
        self.enable()
        with patch.object(OpenAIReplies, 'generate', side_effect=RuntimeError('private token')) as g:
            response = self.client.post(self.path)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private', response.text)
            self.assertEqual(self.client.post(self.path).json()['status'], 'failed')
            g.assert_called_once()

    def test_new_event_during_generation_supersedes(self):
        self.enable()
        def concurrent(history):
            self.ingest(message_id='new', text='Новое сообщение')
            return Draft(reply='Old reply', human_required=False)
        with patch.object(OpenAIReplies, 'generate', side_effect=concurrent):
            result = self.client.post(self.path).json()
            self.assertEqual(result['status'], 'superseded')
            self.assertIsNone(result['text'])

    def test_stale_message_and_parallel_generation_rejected(self):
        self.enable()
        with Session(self.engine) as db:
            db.add(AvitoReply(chat_id=self.chat, message_id=self.message['id'], status='generating'))
            db.commit()
        second = self.ingest(message_id='new').json()
        with patch.object(OpenAIReplies, 'generate') as g:
            self.assertEqual(self.client.post(f"/api/v1/avito/messages/{second['id']}/draft").status_code, 409)
            g.assert_not_called()

    def test_old_message_and_pause_during_generation(self):
        self.enable()
        second = self.ingest(message_id='new').json()
        with patch.object(OpenAIReplies, 'generate') as g:
            self.assertEqual(self.client.post(self.path).status_code, 409)
            g.assert_not_called()
        def pause(history):
            self.client.patch(f'/api/v1/avito/chats/{self.chat}',
                              json=dict(enabled=False, human_required=False))
            return Draft(reply='Obsolete', human_required=False)
        with patch.object(OpenAIReplies, 'generate', side_effect=pause):
            response = self.client.post(f"/api/v1/avito/messages/{second['id']}/draft")
            self.assertEqual(response.json()['status'], 'superseded')
            self.assertIsNone(response.json()['text'])

    def test_cross_owner_and_unauthenticated_access(self):
        credentials = dict(username='other', password='other-password-123')
        self.client.post('/api/v1/auth/register', json=credentials)
        token = self.client.post('/api/v1/auth/login', json=credentials).json()['access_token']
        self.client.headers['Authorization'] = 'Bearer '+token
        self.assertEqual(self.client.get('/api/v1/avito/chats').json(), [])
        self.assertEqual(self.client.get(f'/api/v1/avito/chats/{self.chat}/messages').status_code, 404)
        self.assertEqual(self.enable().status_code, 404)
        self.assertEqual(self.client.post(self.path).status_code, 404)
        self.assertEqual(self.ingest().status_code, 404)
        self.client.headers.pop('Authorization')
        self.assertEqual(self.client.get('/api/v1/avito/chats').status_code, 401)
        self.assertEqual(self.ingest().status_code, 401)

class ProviderTests(unittest.TestCase):
    def test_opt_in_required_and_transport_disabled(self):
        with patch.dict(os.environ, GPT_REPLIES_ENABLED='false'), patch('httpx.Client') as client:
            with self.assertRaises(GenerationUnavailable):
                OpenAIReplies().generate([])
            client.assert_not_called()
        with self.assertRaises(MessengerUnavailable):
            AvitoMessenger().send_text('1', '2', 'test')

    def test_response_request_and_validation(self):
        response = Mock()
        response.json.return_value = dict(status='completed', output=[dict(type='message', content=[
            dict(type='output_text', text='{"reply":"Здравствуйте!","human_required":false}')])])
        with patch.dict(os.environ, GPT_REPLIES_ENABLED='true', OPENAI_API_KEY='synthetic', OPENAI_MODEL='test-model'), patch('httpx.Client') as client:
            post = client.return_value.__enter__.return_value.post
            post.return_value = response
            self.assertFalse(OpenAIReplies().generate([dict(role='user', content='Hi')]).human_required)
            payload = post.call_args.kwargs['json']
            self.assertFalse(payload['store'])
            self.assertEqual(payload['model'], 'test-model')
            response.json.return_value['status'] = 'incomplete'
            with self.assertRaises(GenerationUnavailable):
                OpenAIReplies().generate([])
