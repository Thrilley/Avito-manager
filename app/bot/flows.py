"""Private-chat forms. Drafts live only in memory until confirmation."""
import asyncio
import secrets
import time
from types import SimpleNamespace
from decimal import Decimal
from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from pydantic import ValidationError
from app.shemas import ListingCreate, ListingUpdate
from app.services.telegram_service import CatalogFilter, LinkError, linked_owner, owned_item, edit_owned
from app.services.listing_service import create_listing

MENU = ReplyKeyboardMarkup([['📦 Каталог', '🔎 Поиск'], ['⚙️ Фильтры', '➕ Добавить товар'], ['🗂 Мои товары']], resize_keyboard=True)
ADD_FIELDS = [('title','Как называется товар?'), ('description','Напиши описание товара.'), ('price','Укажи цену в рублях, например 15000 или 15000,50.'), ('brand','Укажи бренд или нажми «Пропустить».'), ('size','Укажи размер или нажми «Пропустить».'), ('condition','Выбери состояние товара.')]
FILTER_FIELDS = [('brand','Какой бренд искать? Можно пропустить.'), ('size','Какой размер искать? Можно пропустить.'), ('price_min','Минимальная цена в рублях? Можно пропустить.'), ('price_max','Максимальная цена в рублях? Можно пропустить.'), ('condition','Выбери состояние или пропусти.')]
BASE = dict(title='Товар',description='',price='1')

async def prompt(update, context):
    draft=context.user_data['draft']
    fields=ADD_FIELDS if draft['mode'] in ('add','edit') else FILTER_FIELDS
    field,text=fields[draft['step']]
    buttons=[['Отмена']]
    if field in ('brand','size','condition') or draft['mode']=='filter':
        buttons.insert(0,['Пропустить'])
    if draft['mode']=='edit':
        buttons.insert(0,['Оставить'])
        current=draft['original'].get(field)
        text+='\nСейчас: '+str(current if current is not None else '—')+'\nМожно оставить без изменений.'
    if field=='condition':
        buttons.insert(0,['Новое','Б/у'])
    await update.effective_message.reply_text(text,reply_markup=ReplyKeyboardMarkup(buttons,resize_keyboard=True))

async def begin(update, context, mode, listing_id=None):
    from app.bot.main import in_db
    try:
        await asyncio.to_thread(in_db,lambda db:linked_owner(db,update.effective_user.id))
    except LinkError as exc:
        await update.effective_message.reply_text(str(exc),reply_markup=MENU)
        return
    context.user_data.pop('search_prompt',None)
    original={}
    if mode=='edit':
        try:
            original=await asyncio.to_thread(in_db,lambda db:owned_item(db,update.effective_user.id,listing_id))
        except (LinkError,LookupError) as exc:
            await update.effective_message.reply_text(str(exc),reply_markup=MENU)
            return
    context.user_data['draft']=dict(mode=mode,step=0,data={},original=original,listing_id=listing_id,nonce=secrets.token_hex(8),started=time.time())
    await prompt(update,context)

async def cancel(update, context):
    context.user_data.pop('draft',None)
    context.user_data.pop('search_prompt',None)
    await update.effective_message.reply_text('Действие отменено.',reply_markup=MENU)

async def input_step(update, context):
    draft=context.user_data.get('draft')
    if draft is None:
        return
    if time.time()-draft['started']>1800:
        context.user_data.pop('draft',None)
        await update.effective_message.reply_text('Время ввода истекло. Начни заново.',reply_markup=MENU)
        return
    fields=ADD_FIELDS if draft['mode'] in ('add','edit') else FILTER_FIELDS
    if draft['step']>=len(fields):
        await update.effective_message.reply_text('Проверь карточку и нажми «Сохранить» или «Отмена».')
        return
    field,_=fields[draft['step']]
    text=update.effective_message.text.strip()
    optional=field in ('brand','size','condition') or draft['mode']=='filter'
    value=None if text=='Пропустить' and optional else text
    keep=draft['mode']=='edit' and text=='Оставить'
    if field=='condition' and value is not None:
        value={'Новое':'new','Б/у':'used'}.get(value,value)
    if field in ('price','price_min','price_max') and value is not None:
        value=value.replace(' ','').replace(',','.')
    if field=='description' and len(text)>2500 and not keep:
        await update.effective_message.reply_text('Описание должно быть не длиннее 2500 символов.')
        return
    candidate=dict(draft['data']) if keep else dict(draft['data'],**{field:value})
    try:
        if draft['mode']=='edit':
            ListingUpdate.model_validate(candidate)
        elif draft['mode']=='add':
            ListingCreate.model_validate(dict(BASE,**candidate))
        else:
            CatalogFilter.model_validate(candidate)
    except ValidationError:
        await update.effective_message.reply_text('Не подходит значение. Проверь поле и введи его ещё раз. Цена должна быть положительной, с точностью до копеек; максимум должен быть не меньше минимума.')
        return
    draft['data']=candidate
    draft['step']+=1
    if draft['step']<len(fields):
        await prompt(update,context)
    elif draft['mode']=='filter':
        from app.bot.main import show_page
        context.user_data['filters']=CatalogFilter.model_validate(candidate).model_dump(mode='json',exclude_none=True)
        context.user_data.pop('draft',None)
        await update.effective_message.reply_text('Фильтры применены.',reply_markup=MENU)
        try:
            await show_page(update,context,0)
        except LinkError as exc:
            await update.effective_message.reply_text(str(exc))
    else:
        preview=dict(draft['original'],**candidate) if draft['mode']=='edit' else candidate
        data=SimpleNamespace(**preview) if draft['mode']=='edit' else ListingCreate.model_validate(preview)
        data.price=Decimal(str(data.price))
        text=(f'Проверь товар:\n{data.title}\n{data.price:.2f} ₽\n'
              f'Бренд: {data.brand or "—"}\nРазмер: {data.size or "—"}\n'
              f'Состояние: { {"new":"Новое","used":"Б/у"}.get(data.condition,"—")}\n\n{data.description}')
        await update.effective_message.reply_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Сохранить',callback_data='save:'+draft['nonce']),InlineKeyboardButton('Отмена',callback_data='cancel:'+draft['nonce'])]]))

async def confirm(update, context):
    from app.bot.main import in_db
    draft=context.user_data.get('draft')
    nonce=update.callback_query.data.split(':',1)[1]
    if not draft or draft['nonce']!=nonce or draft['mode'] not in ('add','edit') or draft['step']!=len(ADD_FIELDS):
        await update.effective_message.reply_text('Эта карточка уже обработана или устарела.',reply_markup=MENU)
        return
    if time.time()-draft['started']>1800:
        await cancel(update,context)
        return
    data=ListingUpdate.model_validate(draft['data']) if draft['mode']=='edit' else ListingCreate.model_validate(draft['data'])
    try:
        def save(db):
            if draft['mode']=='edit':
                return edit_owned(db,update.effective_user.id,draft['listing_id'],data)
            return create_listing(data,db,owner_id=linked_owner(db,update.effective_user.id)).id
        listing_id=await asyncio.to_thread(in_db,save)
    except (LinkError,LookupError) as exc:
        context.user_data.pop('draft',None)
        await update.effective_message.reply_text(str(exc),reply_markup=MENU)
        return
    # Clear before replying: another tap cannot create another product.
    context.user_data.pop('draft',None)
    await update.effective_message.reply_text(f'Товар #{listing_id} сохранён. Открой «Мои товары», чтобы посмотреть его.',reply_markup=MENU)
