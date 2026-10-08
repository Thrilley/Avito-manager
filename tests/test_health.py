import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from app.routers.health import ready, live

class HealthTests(unittest.TestCase):
    def test_live(self):
        self.assertEqual(live(),{'status':'ok'})
    def test_unavailable_database_returns_503(self):
        with patch('app.routers.health.engine') as engine:
            engine.connect.side_effect=RuntimeError('private database connection details')
            with self.assertRaises(HTTPException) as error:
                ready()
            self.assertEqual(error.exception.status_code,503)
            self.assertNotIn('private',error.exception.detail)
    def test_ready_current_migration(self):
        with patch('app.routers.health.engine') as engine:
            connection=engine.connect.return_value.__enter__.return_value
            connection.execute.return_value.scalars.return_value=['0005_avito_replies']
            self.assertEqual(ready(),{'status':'ready'})
