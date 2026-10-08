import unittest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.models import Listing, ExternalListing, SourceAccount, SyncRun, User
from app.integrations.catalog_source import SourceItem, SourcePage, AvitoSource, SourceUnavailable
from app.services.sync_service import synchronize, InvalidSnapshot, SyncConflict

class Adapter:
    def __init__(self, items, complete=True, fail=False):
        self.items, self.complete, self.fail = items, complete, fail
    def pages(self):
        yield SourcePage(items=self.items, complete=self.complete)
        if self.fail:
            raise RuntimeError('secret response body must never be logged')

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine)
        with self.factory() as db:
            user=User(username='owner', password_hash='test')
            db.add(user)
            db.flush()
            self.owner=user.id
            account=SourceAccount(owner_id=user.id, platform='test', account_id='123')
            db.add(account)
            db.commit()
            self.source=account.id
    def tearDown(self):
        self.engine.dispose()
    def item(self, **changes):
        data=dict(external_id='42',title='Nike',price='100.25',description='Shoes',catalog_status='active')
        data.update(changes)
        return SourceItem(**data)
    def sync(self, items, **changes):
        return synchronize(self.factory,self.source,self.owner,Adapter(items,**changes))
    def test_repeat_update_preserves_manual_fields(self):
        self.sync([self.item()])
        with self.factory() as db:
            item=db.scalar(select(Listing))
            item.brand,item.size,item.condition,item.status='Nike','42','used','reserved'
            db.commit()
        self.sync([self.item(title='New title',price='200.00',description=None)])
        with self.factory() as db:
            rows=db.scalars(select(Listing)).all()
            self.assertEqual(len(rows),1)
            self.assertEqual((rows[0].title,rows[0].description,rows[0].brand,rows[0].size,rows[0].condition,rows[0].status),('New title','Shoes','Nike','42','used','reserved'))
            self.assertEqual(len(db.scalars(select(ExternalListing)).all()),1)
    def test_failed_partial_import_keeps_last_snapshot(self):
        self.sync([self.item()])
        with self.assertRaises(RuntimeError):
            self.sync([self.item(title='Wrong')],fail=True)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(Listing)).title,'Nike')
            self.assertTrue(db.scalar(select(ExternalListing)).source_present)
            run=db.scalar(select(SyncRun).order_by(SyncRun.id.desc()))
            self.assertEqual((run.status,run.error_code),('failed','source_failure'))
    def test_incomplete_and_duplicates_rollback(self):
        for items, kwargs in [([self.item()],{'complete':False}),([self.item(),self.item()],{})]:
            with self.assertRaises(InvalidSnapshot):
                self.sync(items,**kwargs)
        with self.factory() as db:
            self.assertEqual(db.scalars(select(Listing)).all(),[])
    def test_missing_and_reappearing(self):
        self.sync([self.item()])
        self.sync([])
        with self.factory() as db:
            self.assertFalse(db.scalar(select(ExternalListing)).source_present)
            self.assertIsNotNone(db.scalar(select(Listing)))
        self.sync([self.item()])
        with self.factory() as db:
            self.assertTrue(db.scalar(select(ExternalListing)).source_present)
            self.assertEqual(len(db.scalars(select(Listing)).all()),1)
    def test_owner_and_parallel_lock(self):
        with self.assertRaises(LookupError):
            synchronize(self.factory,self.source,self.owner+1,Adapter([]))
        with self.factory() as db:
            db.add(SyncRun(source_id=self.source,status='running'))
            db.commit()
        with self.assertRaises(SyncConflict):
            self.sync([])
    def test_unverified_avito_disabled(self):
        with self.assertRaises(SourceUnavailable):
            synchronize(self.factory,self.source,self.owner,AvitoSource())
