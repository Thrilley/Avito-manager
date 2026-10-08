"""Run as a separate process: python -m app.bot.main."""
import asyncio
import json
import logging
import os
import shlex
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from pydantic import ValidationError
from app.database import SessionLocal
from app.services.telegram_service import consume_code, linked_owner, catalog_page, item_card, CatalogFilter, LinkError
from app.services.listing_service import create_listing
from app.shemas import ListingCreate
from app.bot.flows import MENU, begin, cancel, input_step, confirm
from app.bot.management import show_owned, manage_button, card_buttons, card_text

HELP = ('Каталог владельца:\n/link КОД — привязка\n/catalog — товары\n/search Nike — поиск\n'
        '/filter brand=Nike size=42 price_max=20000 — фильтры\n/item ID — карточка\n'
        '/my — все мои товары\n/add — добавить товар пошагово\n/cancel — отменить ввод\n'
        'Код привязки получи в API: POST /api/v1/telegram/link-code.')

def in_db(action):
    with SessionLocal() as db:
        return action(db)

def private(update):
    return update.effective_chat is not None and update.effective_chat.type == 'private' and update.effective_user is not None

async def start(update, context):
    if private(update):
        context.user_data.pop("draft",None)
        context.user_data.pop("search_prompt",None)
        await update.effective_message.reply_text(HELP,reply_markup=MENU)

async def link(update, context):
    if not private(update):
        return
    if len(context.args) != 1:
        await update.effective_message.reply_text('Используй /link КОД в личном чате.')
        return
    try:
        await asyncio.to_thread(in_db, lambda db: consume_code(db, update.effective_user.id, context.args[0]))
        context.user_data.clear()
        await update.effective_message.reply_text('Аккаунт привязан. Открой каталог кнопкой ниже.',reply_markup=MENU)
    except LinkError as exc:
        await update.effective_message.reply_text(str(exc))

async def show_page(update, context, page):
    data, more = await asyncio.to_thread(in_db, lambda db: catalog_page(db,update.effective_user.id,CatalogFilter.model_validate(context.user_data.get('filters',{})),page))
    text = '\n\n'.join(f"#{x['id']} · {x['title']}\n{x['price']} ₽ · размер {x['size'] or 'не указан'}\n/item {x['id']}" for x in data) or 'Товары не найдены.'
    rows=[[InlineKeyboardButton(f"Открыть #{x['id']}",callback_data=f"item:{x['id']}")] for x in data]
    buttons=[]
    if page:
        buttons.append(InlineKeyboardButton('Назад',callback_data=f'page:{page-1}'))
    if more:
        buttons.append(InlineKeyboardButton('Далее',callback_data=f'page:{page+1}'))
    if buttons:
        rows.append(buttons)
    await update.effective_message.reply_text(text,reply_markup=InlineKeyboardMarkup(rows) if rows else None)

async def catalog(update, context):
    if not private(update):
        return
    try:
        command=update.effective_message.text.split()[0].split('@')[0]
        if command == '/search':
            filters=CatalogFilter(q=' '.join(context.args))
        elif command == '/filter':
            raw=update.effective_message.text.partition(' ')[2]
            filters=CatalogFilter.model_validate(dict(part.split('=',1) for part in shlex.split(raw)))
        else:
            filters=CatalogFilter()
        context.user_data['filters']=filters.model_dump(mode='json',exclude_none=True)
        await show_page(update,context,0)
    except (ValidationError,ValueError):
        await update.effective_message.reply_text('Проверь фильтры. Пример: /filter brand=Nike size=42 price_max=20000')
    except LinkError as exc:
        await update.effective_message.reply_text(str(exc))

async def page(update, context):
    if not private(update):
        return
    await update.callback_query.answer()
    try:
        await show_page(update,context,int(update.callback_query.data.split(':')[1]))
    except (LinkError,ValueError) as exc:
        await update.effective_message.reply_text(str(exc))

async def item(update, context):
    if not private(update):
        return
    try:
        if len(context.args)!=1:
            raise ValueError()
        data=await asyncio.to_thread(in_db,lambda db:item_card(db,update.effective_user.id,int(context.args[0])))
        text=f"#{data['id']} · {data['title']}\n{data['price']} ₽\nБренд: {data['brand'] or '—'}\nРазмер: {data['size'] or '—'}\nСостояние: {data['condition'] or '—'}\n\n{data['description'][:2500]}"
        await update.effective_message.reply_text(text,reply_markup=card_buttons(data['id']))
    except ValueError:
        await update.effective_message.reply_text('Используй /item ID')
    except (LinkError,LookupError) as exc:
        await update.effective_message.reply_text(str(exc))

async def add(update, context):
    if not private(update):
        return
    if not update.effective_message.text.partition(' ')[2].strip():
        await begin(update,context,'add')
        return
    try:
        data=ListingCreate.model_validate_json(update.effective_message.text.partition(' ')[2])
        def create(db):
            owner=linked_owner(db,update.effective_user.id)
            return create_listing(data,db,owner_id=owner).id
        listing_id=await asyncio.to_thread(in_db,create)
        await update.effective_message.reply_text(f'Товар #{listing_id} добавлен в локальный каталог.')
    except (ValidationError,ValueError):
        await update.effective_message.reply_text('Пример: /add {"title":"Nike","description":"Кроссовки","price":"10000"}')
    except LinkError as exc:
        await update.effective_message.reply_text(str(exc))


async def my_items(update,context):
    if private(update):
        await show_owned(update,context)

async def cancel_command(update,context):
    if private(update):
        await cancel(update,context)

async def text_message(update,context):
    if not private(update):
        return
    text=update.effective_message.text.strip()
    if text=='Отмена':
        await cancel(update,context)
    elif text=='➕ Добавить товар':
        await begin(update,context,'add')
    elif text=='⚙️ Фильтры':
        await begin(update,context,'filter')
    elif text=='📦 Каталог':
        context.user_data.pop('draft',None)
        context.user_data.pop('search_prompt',None)
        await catalog(update,context)
    elif text=='🗂 Мои товары':
        context.user_data.pop('draft',None)
        context.user_data.pop('search_prompt',None)
        await show_owned(update,context)
    elif text=='🔎 Поиск':
        context.user_data.pop('draft',None)
        context.user_data['search_prompt']=True
        await update.effective_message.reply_text('Напиши название или часть описания товара. /cancel — отмена.')
    elif context.user_data.get('draft'):
        await input_step(update,context)
    elif context.user_data.pop('search_prompt',False):
        try:
            context.user_data['filters']=CatalogFilter(q=text).model_dump(mode='json',exclude_none=True)
            await show_page(update,context,0)
        except (ValidationError,LinkError) as exc:
            await update.effective_message.reply_text(str(exc) if isinstance(exc,LinkError) else 'Введите запрос от 1 до 250 символов.',reply_markup=MENU)
    else:
        await update.effective_message.reply_text('Выбери действие кнопкой ниже.',reply_markup=MENU)

async def button(update,context):
    if not private(update):
        return
    kind,value=update.callback_query.data.split(':',1)
    if kind=='page':
        await page(update,context)
        return
    await update.callback_query.answer()
    if kind in ('mpage','mitem','edit','status','setstatus'):
        await manage_button(update,context,kind,value)
    elif kind=='save':
        await confirm(update,context)
    elif kind=='cancel':
        draft=context.user_data.get('draft')
        if draft and draft['nonce']==value:
            await cancel(update,context)
    elif kind=='item':
        try:
            data=await asyncio.to_thread(in_db,lambda db:item_card(db,update.effective_user.id,int(value)))
            text=f"#{data['id']} · {data['title']}\n{data['price']} ₽\nБренд: {data['brand'] or '—'}\nРазмер: {data['size'] or '—'}\nСостояние: { {'new':'Новое','used':'Б/у'}.get(data['condition'],'—')}\n\n{data['description'][:2500]}"
            await update.effective_message.reply_text(text,reply_markup=card_buttons(data['id']))
        except (ValueError,LinkError,LookupError) as exc:
            await update.effective_message.reply_text(str(exc))

async def error(update, context):
    # Do not log updates, token-bearing URLs or exception text.
    logging.getLogger(__name__).error('Bot operation failed: %s',type(context.error).__name__)
    if update and private(update):
        await update.effective_message.reply_text('Не удалось выполнить операцию. Попробуй позже.')

def build_application(token):
    application=Application.builder().token(token).concurrent_updates(False).build()
    for names,handler in [(['start','help'],start),(['link'],link),(['catalog','search','filter'],catalog),(['item'],item),(['add'],add),(['cancel'],cancel_command),(['my'],my_items)]:
        application.add_handler(CommandHandler(names,handler))
    application.add_handler(CallbackQueryHandler(button,pattern=r'^(?:(page|item|save|cancel|mpage|mitem|edit|status):[a-zA-Z0-9]+|setstatus:[0-9]+:(active|reserved|sold|archived))$'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_message))
    application.add_error_handler(error)
    return application

def main():
    token=os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise SystemExit('Set TELEGRAM_BOT_TOKEN in local .env; do not share it in chat.')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    build_application(token).run_polling(allowed_updates=['message','callback_query'])

if __name__=='__main__':
    main()
