import unittest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests import test_bot_flows
from app.models import Listing, User
from app.bot.main import button
from app.bot.flows import input_step
from app.services.telegram_service import owned_page

class ManagementTests(unittest.IsolatedAsyncioTestCase):
    setUp=test_bot_flows.FormTests.setUp
    tearDown=test_bot_flows.FormTests.tearDown
    update=test_bot_flows.FormTests.update
    fill=test_bot_flows.FormTests.fill
    count=test_bot_flows.FormTests.count

    async def saved_item(self):
        nonce=await self.fill()
        await button(self.update(data='save:'+nonce),self.context)
        with Session(self.engine) as db:
            return db.scalar(select(Listing.id))

    async def test_edit_keeps_status_and_unchanged_fields(self):
        listing_id=await self.saved_item()
        with Session(self.engine) as db:
            db.get(Listing,listing_id).status='sold'
            db.commit()
        await button(self.update(data=f'edit:{listing_id}'),self.context)
        for text in ['Nike Updated','Оставить','Оставить','Оставить','Оставить','Оставить']:
            await input_step(self.update(text),self.context)
        nonce=self.context.user_data['draft']['nonce']
        await button(self.update(data='save:'+nonce),self.context)
        with Session(self.engine) as db:
            row=db.get(Listing,listing_id)
            self.assertEqual((row.title,row.description,row.brand,row.size,row.status),('Nike Updated','Кроссовки','Nike','42','sold'))
        self.assertEqual(self.count(),1)

    async def test_optional_field_cleared(self):
        listing_id=await self.saved_item()
        await button(self.update(data=f'edit:{listing_id}'),self.context)
        for text in ['Оставить','Оставить','Оставить','Пропустить','Оставить','Оставить']:
            await input_step(self.update(text),self.context)
        nonce=self.context.user_data['draft']['nonce']
        await button(self.update(data='save:'+nonce),self.context)
        with Session(self.engine) as db:
            self.assertIsNone(db.get(Listing,listing_id).brand)

    async def test_status_update_and_management_listing(self):
        listing_id=await self.saved_item()
        for status in ['reserved','sold','archived','active']:
            await button(self.update(data=f'setstatus:{listing_id}:{status}'),self.context)
            with Session(self.engine) as db:
                self.assertEqual(db.get(Listing,listing_id).status,status)
                rows,_=owned_page(db,123)
                self.assertEqual(len(rows),1)
        message=self.update(data=f'mitem:{listing_id}')
        await button(message,self.context)
        self.assertIn('В наличии',message.effective_message.reply_text.call_args.args[0])

    async def test_forged_foreign_buttons_cannot_modify(self):
        with Session(self.engine) as db:
            other=User(username='other',password_hash='test')
            db.add(other)
            db.flush()
            row=Listing(title='Foreign',description='Private',price=100,status='active',owner_id=other.id)
            db.add(row)
            db.commit()
            listing_id=row.id
        for data in [f'mitem:{listing_id}',f'edit:{listing_id}',f'status:{listing_id}',f'setstatus:{listing_id}:sold']:
            message=self.update(data=data)
            await button(message,self.context)
            self.assertIn('не найден',message.effective_message.reply_text.call_args.args[0])
        with Session(self.engine) as db:
            self.assertEqual(db.get(Listing,listing_id).status,'active')
        self.assertNotIn('draft',self.context.user_data)

    async def test_deleted_item_during_edit_not_recreated(self):
        listing_id=await self.saved_item()
        await button(self.update(data=f'edit:{listing_id}'),self.context)
        for _ in range(6):
            await input_step(self.update('Оставить'),self.context)
        nonce=self.context.user_data['draft']['nonce']
        with Session(self.engine) as db:
            db.delete(db.get(Listing,listing_id))
            db.commit()
        await button(self.update(data='save:'+nonce),self.context)
        self.assertEqual(self.count(),0)
        self.assertNotIn('draft',self.context.user_data)
