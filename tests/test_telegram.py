import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.models import User, Listing, ExternalListing, TelegramLinkCode, TelegramBinding
from app.services.telegram_service import issue_code, consume_code, unlink, LinkError, CatalogFilter, catalog_page, item_card
from app.bot.main import catalog, add, link, build_application

class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        users=[User(username='one',password_hash='test'),User(username='two',password_hash='test')]
        self.db.add_all(users)
        self.db.commit()
        self.owner,self.other=users[0].id,users[1].id
    def tearDown(self):
        self.db.close()
        self.engine.dispose()
    def bind(self,telegram_id=123):
        code=issue_code(self.db,self.owner)
        consume_code(self.db,telegram_id,code)
        return code
    def create(self,**changes):
        data=dict(title='Nike',description='Shoes',price='100.25',status='active',owner_id=self.owner,brand='Nike',size='42')
        data.update(changes)
        row=Listing(**data)
        self.db.add(row)
        self.db.commit()
        return row
    def test_single_use_hash_and_expiration(self):
        code=self.bind()
        row=self.db.scalar(select(TelegramLinkCode))
        self.assertNotEqual(row.code_hash,code)
        with self.assertRaises(LinkError):
            consume_code(self.db,124,code)
        unlink(self.db,self.owner)
        code=issue_code(self.db,self.owner)
        row=self.db.scalar(select(TelegramLinkCode).where(TelegramLinkCode.used_at.is_(None)))
        row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(LinkError):
            consume_code(self.db,123,code)
        self.assertIsNone(self.db.scalar(select(TelegramBinding)))
    def test_reissued_code_invalidates_old(self):
        old=issue_code(self.db,self.owner)
        new=issue_code(self.db,self.owner)
        with self.assertRaises(LinkError):
            consume_code(self.db,123,old)
        self.assertEqual(consume_code(self.db,123,new),self.owner)
    def test_access_filters_and_unlink(self):
        self.bind()
        own=self.create()
        foreign=self.create(owner_id=self.other)
        self.create(status='sold')
        rows,more=catalog_page(self.db,123,CatalogFilter(q='nike',brand='Nike',size='42',price_max='101'))
        self.assertEqual([r['id'] for r in rows],[own.id])
        with self.assertRaises(LookupError):
            item_card(self.db,123,foreign.id)
        unlink(self.db,self.owner)
        with self.assertRaises(LinkError):
            catalog_page(self.db,123,CatalogFilter())
    def test_external_availability_and_pagination(self):
        self.bind()
        for state,present in [('active',True),('archived',True),('active',False),(None,True)]:
            row=self.create()
            self.db.add(ExternalListing(listing_id=row.id,platform='test',account_id='x',external_id=str(row.id),source_present=present,source_data={'catalog_status':state} if state else None))
        for _ in range(6):
            self.create()
        self.db.commit()
        rows,more=catalog_page(self.db,123,CatalogFilter())
        self.assertEqual(len(rows),5)
        self.assertTrue(more)
        rows,more=catalog_page(self.db,123,CatalogFilter(),page=1)
        self.assertEqual(len(rows),2)
        self.assertFalse(more)
    def test_blocked_owner_denied(self):
        self.bind()
        self.db.get(User,self.owner).is_active=False
        self.db.commit()
        with self.assertRaises(LinkError):
            catalog_page(self.db,123,CatalogFilter())

class HandlerTests(unittest.IsolatedAsyncioTestCase):
    def update(self,text,kind='private'):
        return SimpleNamespace(effective_chat=SimpleNamespace(type=kind),effective_user=SimpleNamespace(id=123),effective_message=SimpleNamespace(text=text,reply_text=AsyncMock()))
    async def test_group_ignored(self):
        update=self.update('/catalog','group')
        await catalog(update,SimpleNamespace(args=[],user_data={}))
        update.effective_message.reply_text.assert_not_awaited()
    async def test_catalog_reply_without_telegram(self):
        update=self.update('/catalog')
        with patch('app.bot.main.in_db',return_value=([dict(id=1,title='Nike',price='100.25',size='42')],False)):
            await catalog(update,SimpleNamespace(args=[],user_data={}))
        self.assertIn('Nike',update.effective_message.reply_text.call_args.args[0])
    async def test_add_validates_and_reports_local_creation(self):
        update=self.update('/add {"title":"Nike","description":"Shoes","price":"100"}')
        with patch('app.bot.main.in_db',return_value=7):
            await add(update,SimpleNamespace(args=[]))
        self.assertIn('#7',update.effective_message.reply_text.call_args.args[0])
    def test_application_builds_offline(self):
        app=build_application('123456:TEST_ONLY_NOT_A_REAL_BOT_TOKEN')
        self.assertEqual(len(app.handlers[0]),9)
