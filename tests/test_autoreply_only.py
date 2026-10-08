import unittest
from fastapi.testclient import TestClient
from main import app
from app.services.avito_reply_service import requests_operator
from scripts.demo_autoreply import run
from unittest.mock import patch

class ScopeTests(unittest.TestCase):
    def test_only_autoreplier_routes(self):
        paths = app.openapi()['paths']
        self.assertIn('/api/v1/avito/chats', paths)
        self.assertFalse(any(x in p for p in paths for x in ('catalog', 'listings', 'telegram', '/sync')))
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/v1/listings').status_code, 404)
            self.assertEqual(client.get('/api/v1/avito/chats').status_code, 401)

    def test_operator_requests(self):
        for text in ('Соедините с оператором', 'Позовите продавца', 'Нужен живой человек', 'Хочу поговорить с менеджером', 'Оператор!'):
            self.assertTrue(requests_operator(text), text)
        for text in ('Есть размер 43?', 'Какая цена?', 'Не нужен оператор', 'Оператор уже ответил'):
            self.assertFalse(requests_operator(text), text)

    def test_offline_demo_never_calls_provider(self):
        with patch('httpx.Client') as network, patch('builtins.print') as output:
            run()
            network.assert_not_called()
            output.assert_any_call('Чат передан оператору:', True)
            output.assert_any_call('Автоответчик приостановлен:', True)
