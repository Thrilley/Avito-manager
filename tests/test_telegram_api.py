import unittest
from tests import test_catalog

class TelegramApiTests(unittest.TestCase):
    setUp=test_catalog.CatalogTests.setUp
    tearDown=test_catalog.CatalogTests.tearDown
    def test_issue_code_and_revoke(self):
        response=self.client.post('/api/v1/telegram/link-code')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(response.json()['expires_in'],600)
        self.assertEqual(self.client.delete('/api/v1/telegram/binding').status_code,204)
        self.client.headers.pop('Authorization')
        self.assertEqual(self.client.post('/api/v1/telegram/link-code').status_code,401)
