import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.models import User, TelegramBinding, Listing
from app.bot.main import text_message, button
from app.bot.flows import begin, input_step, cancel

class FormTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            owner=User(username='owner',password_hash='test')
            db.add(owner)
            db.flush()
            self.owner=owner.id
            db.add(TelegramBinding(telegram_id=123,owner_id=owner.id))
            db.commit()
        def in_db(action):
            with Session(self.engine) as db:
                return action(db)
        self.patcher=patch('app.bot.main.in_db',side_effect=in_db)
        self.patcher.start()
        self.context=SimpleNamespace(user_data={},args=[])
    def tearDown(self):
        self.patcher.stop()
        self.engine.dispose()
    def update(self,text='',data=None,user_id=123):
        return SimpleNamespace(effective_chat=SimpleNamespace(type='private'),effective_user=SimpleNamespace(id=user_id),effective_message=SimpleNamespace(text=text,reply_text=AsyncMock()),callback_query=SimpleNamespace(data=data,answer=AsyncMock()) if data else None)
    async def fill(self):
        await begin(self.update(),self.context,'add')
        for text in ['Nike Air','Кроссовки','15000,50','Nike','42','Б/у']:
            await input_step(self.update(text),self.context)
        return self.context.user_data['draft']['nonce']
    def count(self):
        with Session(self.engine) as db:
            return db.scalar(select(func.count()).select_from(Listing))
    async def test_full_form_confirm_once(self):
        nonce=await self.fill()
        self.assertEqual(self.count(),0)
        await button(self.update(data='save:'+nonce),self.context)
        await button(self.update(data='save:'+nonce),self.context)
        self.assertEqual(self.count(),1)
        with Session(self.engine) as db:
            item=db.scalar(select(Listing))
            self.assertEqual((item.title,item.brand,item.size,item.condition,item.owner_id),('Nike Air','Nike','42','used',self.owner))
            self.assertEqual(str(item.price),'15000.50')
    async def test_invalid_price_keeps_step(self):
        await begin(self.update(),self.context,'add')
        for text in ['Nike','Shoes']:
            await input_step(self.update(text),self.context)
        for text in ['0','-1','abc','NaN','1.001']:
            await input_step(self.update(text),self.context)
            self.assertEqual(self.context.user_data['draft']['step'],2)
        await input_step(self.update('100'),self.context)
        self.assertEqual(self.context.user_data['draft']['step'],3)
    async def test_skip_and_cancel(self):
        await begin(self.update(),self.context,'add')
        for text in ['Nike','Shoes','100','Пропустить','Пропустить','Пропустить']:
            await input_step(self.update(text),self.context)
        self.assertIsNone(self.context.user_data['draft']['data']['brand'])
        await cancel(self.update(),self.context)
        self.assertNotIn('draft',self.context.user_data)
        self.assertEqual(self.count(),0)
    async def test_stale_confirmation_ignored(self):
        nonce=await self.fill()
        await begin(self.update(),self.context,'add')
        await button(self.update(data='save:'+nonce),self.context)
        self.assertEqual(self.count(),0)
    async def test_revoked_binding_blocks_save(self):
        nonce=await self.fill()
        with Session(self.engine) as db:
            db.delete(db.scalar(select(TelegramBinding)))
            db.commit()
        await button(self.update(data='save:'+nonce),self.context)
        self.assertEqual(self.count(),0)
    async def test_filter_steps_and_price_range(self):
        await begin(self.update(),self.context,'filter')
        for text in ['Nike','42','100','50']:
            await input_step(self.update(text),self.context)
        self.assertEqual(self.context.user_data['draft']['step'],3)
        await input_step(self.update('200'),self.context)
        await input_step(self.update('Пропустить'),self.context)
        self.assertEqual(self.context.user_data['filters']['brand'],'Nike')
        self.assertNotIn('draft',self.context.user_data)
    async def test_unlinked_cannot_start_form(self):
        await begin(self.update(user_id=999),self.context,'add')
        self.assertNotIn('draft',self.context.user_data)
    async def test_expired_draft_does_not_save(self):
        nonce=await self.fill()
        self.context.user_data['draft']['started']=time.time()-1801
        await button(self.update(data='save:'+nonce),self.context)
        self.assertEqual(self.count(),0)
    async def test_search_and_item_buttons(self):
        await text_message(self.update('🔎 Поиск'),self.context)
        self.assertTrue(self.context.user_data['search_prompt'])
        await text_message(self.update('Nike'),self.context)
        self.assertEqual(self.context.user_data['filters']['q'],'Nike')
        nonce=await self.fill()
        await button(self.update(data='save:'+nonce),self.context)
        message=self.update(data='item:1')
        await button(message,self.context)
        self.assertIn('Nike Air',message.effective_message.reply_text.call_args.args[0])
