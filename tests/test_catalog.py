import unittest
import os
from unittest.mock import patch
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.routers.listing import get_db
from app.legacy_app import app

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, JWT_SECRET="test-only-signing-key-32-bytes-minimum")
        self.env_patch.start()
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        def db_override():
            with Session(self.engine) as session:
                yield session
        app.dependency_overrides[get_db] = db_override
        self.client = TestClient(app)
        credentials = dict(username='owner', password='test-password-123')
        assert self.client.post('/api/v1/auth/register', json=credentials).status_code == 201
        response = self.client.post('/api/v1/auth/login', json=credentials)
        assert response.status_code == 200, response.text
        self.client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.env_patch.stop()

    def create(self, **changes):
        data = dict(title='Nike', description='Shoes', price='120.25', brand='Nike', size='42', condition='used')
        data.update(changes)
        response = self.client.post('/api/v1/listings', json=data)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_filters_pagination_and_exact_price(self):
        first = self.create()
        self.create(title='Adidas', brand='Adidas')
        response = self.client.get('/api/v1/listings', params=dict(q='nike', brand='Nike', size='42', condition='used', price_min='120', price_max='121'))
        self.assertEqual([x['id'] for x in response.json()], [first['id']])
        self.assertEqual(Decimal(response.json()[0]['price']), Decimal('120.25'))
        self.assertEqual(len(self.client.get('/api/v1/listings?limit=1&offset=1').json()), 1)
        self.assertEqual(self.client.get('/api/v1/listings?price_min=200&price_max=100').status_code, 422)
        self.assertEqual(self.client.get('/api/v1/listings?limit=101').status_code, 422)

    def test_update_clear_status_and_legacy(self):
        item = self.create()
        path = f"/api/v1/listings/{item['id']}"
        self.assertIsNone(self.client.patch(path, json={'brand': None}).json()['brand'])
        self.assertEqual(self.client.patch(path+'/status', json={'status': 'sold'}).json()['status'], 'sold')
        self.assertEqual(self.client.get(f"/listings/{item['id']}").status_code, 200)
        self.assertEqual(self.client.delete(path).status_code, 204)
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_literal_search_and_fractional_price_validation(self):
        self.create()
        self.assertEqual(self.client.get('/api/v1/listings?q=%25').json(), [])
        self.assertEqual(self.client.post('/api/v1/listings', json=dict(title='Nike', description='Shoes', price='1.001')).status_code, 422)
