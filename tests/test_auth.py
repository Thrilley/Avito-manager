from datetime import datetime, timedelta, timezone
import jwt
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import User, Listing
from app.core.security import ISSUER, AUDIENCE, signing_key, verify_password
import unittest
from tests import test_catalog

class AuthTests(unittest.TestCase):
    setUp = test_catalog.CatalogTests.setUp
    tearDown = test_catalog.CatalogTests.tearDown
    create = test_catalog.CatalogTests.create
    def test_private_catalog_and_legacy_routes(self):
        item = self.create()
        other = dict(username='other', password='other-password-123')
        self.assertEqual(self.client.post('/api/v1/auth/register', json=other).status_code, 201)
        token = self.client.post('/api/v1/auth/login', json=other).json()['access_token']
        self.client.headers['Authorization'] = 'Bearer '+token
        self.assertEqual(self.client.get('/api/v1/listings').json(), [])
        self.assertEqual(self.client.get('/listings').json(), [])
        self.assertEqual(self.client.get('/listing/search?search=Nike').json(), [])
        self.assertEqual(self.client.get('/listing/filter').json(), [])
        self.assertEqual(self.client.get('/listing/sort?sort=price&sort_plan=asc').json(), [])
        for method, path, body in [('GET', f"/api/v1/listings/{item['id']}", None), ('PATCH', f"/api/v1/listings/{item['id']}", {'title':'Stolen'}), ('DELETE', f"/api/v1/listings/{item['id']}", None), ('GET', f"/listings/{item['id']}", None), ('PATCH', f"/listing/{item['id']}", {'title':'Stolen'}), ('DELETE', f"/listing/{item['id']}", None), ('PATCH', f"/listing/staty/{item['id']}?status=sold", None), ('PATCH', f"/api/v1/listings/{item['id']}/status", {'status':'sold'})]:
            self.assertEqual(self.client.request(method, path, json=body).status_code, 404)

    def test_passwords_and_role_escalation(self):
        data = dict(username='owner', password='test-password-123')
        self.assertEqual(self.client.post('/api/v1/auth/register', json=data).status_code, 409)
        self.assertEqual(self.client.post('/api/v1/auth/register', json=dict(username='hacker', password='test-password-123', is_admin=True)).status_code, 422)
        self.assertFalse(self.client.get('/api/v1/auth/me').json()['is_admin'])
        self.assertEqual(self.client.get('/api/v1/auth/users').status_code, 403)
        self.assertEqual(self.client.post('/api/v1/auth/login', json=dict(username='owner', password='wrong-password-123')).status_code, 401)
        with Session(self.engine) as db:
            user = db.scalar(select(User).where(User.username == 'owner'))
            self.assertNotEqual(user.password_hash, data['password'])
            self.assertTrue(verify_password(data['password'], user.password_hash))
            user.is_active = False
            db.commit()
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code, 401)

    def test_invalid_expired_and_missing_tokens(self):
        self.client.headers.pop('Authorization')
        self.assertEqual(self.client.get('/api/v1/listings').status_code, 401)
        now = datetime.now(timezone.utc)
        claims = dict(sub='1', iat=now-timedelta(hours=1), exp=now-timedelta(minutes=1), iss=ISSUER, aud=AUDIENCE)
        for token in ['garbage', jwt.encode(claims, signing_key(), algorithm='HS256'), jwt.encode(dict(claims, exp=now+timedelta(minutes=1)), 'different-key-at-least-32-bytes-long', algorithm='HS256')]:
            self.client.headers['Authorization'] = 'Bearer '+token
            self.assertEqual(self.client.get('/api/v1/listings').status_code, 401)

    def test_legacy_unassigned_hidden(self):
        with Session(self.engine) as db:
            db.add(Listing(title='Old', description='Legacy', price=100, status='active'))
            db.commit()
        self.assertEqual(self.client.get('/api/v1/listings').json(), [])

    def test_admin_permission_without_catalog_bypass(self):
        with Session(self.engine) as db:
            user = db.scalar(select(User).where(User.username == 'owner'))
            user.is_admin = True
            db.commit()
        response = self.client.get('/api/v1/auth/users')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('password_hash', response.json()[0])
