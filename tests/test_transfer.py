import unittest
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from app.database import Base
from app.models import User, Listing, TelegramBinding, SourceAccount, ExternalListing, SyncRun
from scripts.transfer_sqlite import transfer, TransferError

class TransferTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/'source.db'
        self.source=create_engine(f'sqlite:///{self.path}')
        self.target=create_engine(f'sqlite:///{Path(self.folder.name)/"target.db"}')
        for engine in [self.source,self.target]:
            Base.metadata.create_all(engine)
            with engine.begin() as db:
                db.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
                db.execute(text("INSERT INTO alembic_version VALUES ('0005_avito_replies')"))
        with Session(self.source) as db:
            user=User(id=10,username='owner',password_hash='test-hash')
            db.add(user)
            db.flush()
            listing=Listing(id=25,owner_id=user.id,title='Nike',description='Shoes',price='100.25',status='reserved')
            db.add(listing)
            db.flush()
            account=SourceAccount(id=30,owner_id=user.id,platform='test',account_id='account')
            db.add(account)
            db.flush()
            db.add_all([TelegramBinding(telegram_id=9876543210,owner_id=user.id),ExternalListing(listing_id=listing.id,platform='test',account_id='account',external_id='42',source_data={'price':'100.25','catalog_status':'active'}),SyncRun(source_id=account.id,status='succeeded')])
            db.commit()
    def tearDown(self):
        self.source.dispose()
        self.target.dispose()
        self.folder.cleanup()
    def test_dry_run_changes_neither_database(self):
        counts=transfer(self.path,self.target)
        self.assertEqual(counts['listing'],1)
        with Session(self.target) as db:
            self.assertIsNone(db.scalar(select(Listing)))
        with Session(self.source) as db:
            self.assertEqual(db.get(Listing,25).status,'reserved')
    def test_apply_preserves_ids_bindings_and_source(self):
        transfer(self.path,self.target,apply=True)
        with Session(self.target) as db:
            self.assertEqual(db.get(Listing,25).owner_id,10)
            self.assertEqual(str(db.get(Listing,25).price),'100.25')
            self.assertEqual(db.scalar(select(TelegramBinding)).telegram_id,9876543210)
            self.assertEqual(db.scalar(select(ExternalListing)).source_data['price'],'100.25')
            item=Listing(owner_id=10,title='Next',description='',price=50,status='active')
            db.add(item)
            db.commit()
            self.assertGreater(item.id,25)
    def test_nonempty_target_refused(self):
        transfer(self.path,self.target,apply=True)
        with self.assertRaises(TransferError):
            transfer(self.path,self.target,apply=True)
        with Session(self.target) as db:
            self.assertEqual(db.get(Listing,25).title,'Nike')
    def test_schema_mismatch_refused(self):
        with self.target.begin() as db:
            db.execute(text("UPDATE alembic_version SET version_num='0003_sync'"))
        with self.assertRaises(TransferError):
            transfer(self.path,self.target)
    def test_source_cannot_be_target(self):
        with self.assertRaises(TransferError):
            transfer(self.path,self.source,apply=True)
