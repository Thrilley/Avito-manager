import os
import sys
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class MigrationTests(unittest.TestCase):
    def migrate(self, path):
        env = dict(os.environ, DATABASE_URL=f'sqlite:///{path}')
        env.pop('DATABASE_HOST', None)
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, env=env, check=True, capture_output=True)

    def test_fresh_and_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'new.db'
            self.migrate(path)
            self.migrate(path)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM listing').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM external_listing').fetchone()[0], 0)
                for table in ('avito_chat', 'avito_message', 'avito_reply'):
                    self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0], '0005_avito_replies')

    def test_legacy_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'legacy.db'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE listing (id INTEGER PRIMARY KEY, title VARCHAR, description VARCHAR, price FLOAT, created_at DATETIME, status VARCHAR)')
                db.execute("INSERT INTO listing VALUES (7,'Nike','Shoes',123.45,'2026-01-01 12:00:00','active')")
                db.commit()
            self.migrate(path)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT id,title,price,currency FROM listing').fetchone(), (7,'Nike',123.45,'RUB'))
