import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app.services.telegram_service import owned_page, owned_item, edit_owned, LinkError
from app.shemas import ListingUpdate
from app.bot.flows import MENU

STATUSES={'active':'В наличии','reserved':'Забронирован','sold':'Продан','archived':'В архиве'}

def card_text(data):
    return (f"#{data['id']} · {data['title']}\n{data['price']} ₽\n"
            f"Статус: {STATUSES.get(data['status'],data['status'])}\n"
            f"Бренд: {data['brand'] or '—'}\nРазмер: {data['size'] or '—'}\n"
            f"Состояние: { {'new':'Новое','used':'Б/у'}.get(data['condition'],'—')}\n\n{data['description'][:2500]}")

def card_buttons(listing_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton('Редактировать',callback_data=f'edit:{listing_id}'),InlineKeyboardButton('Изменить статус',callback_data=f'status:{listing_id}')]])

async def show_owned(update,context,page=0):
    from app.bot.main import in_db
    try:
        rows,more=await asyncio.to_thread(in_db,lambda db:owned_page(db,update.effective_user.id,page))
        text='\n\n'.join(f"#{r['id']} · {r['title']}\n{r['price']} ₽ · {STATUSES.get(r['status'],r['status'])}" for r in rows) or 'У тебя пока нет товаров.'
        buttons=[[InlineKeyboardButton(f"Открыть #{r['id']}",callback_data=f"mitem:{r['id']}")] for r in rows]
        navigation=[]
        if page:
            navigation.append(InlineKeyboardButton('Назад',callback_data=f'mpage:{page-1}'))
        if more:
            navigation.append(InlineKeyboardButton('Далее',callback_data=f'mpage:{page+1}'))
        if navigation:
            buttons.append(navigation)
        await update.effective_message.reply_text(text,reply_markup=InlineKeyboardMarkup(buttons) if buttons else MENU)
    except (LinkError,ValueError) as exc:
        await update.effective_message.reply_text(str(exc),reply_markup=MENU)

async def manage_button(update,context,kind,value):
    from app.bot.main import in_db
    from app.bot.flows import begin
    try:
        if kind=='mpage':
            await show_owned(update,context,int(value))
        elif kind=='edit':
            await begin(update,context,'edit',int(value))
        elif kind=='mitem':
            data=await asyncio.to_thread(in_db,lambda db:owned_item(db,update.effective_user.id,int(value)))
            await update.effective_message.reply_text(card_text(data),reply_markup=card_buttons(data['id']))
        elif kind=='status':
            data=await asyncio.to_thread(in_db,lambda db:owned_item(db,update.effective_user.id,int(value)))
            buttons=[[InlineKeyboardButton(label,callback_data=f'setstatus:{value}:{status}')] for status,label in STATUSES.items()]
            await update.effective_message.reply_text(f"Выбери статус товара #{data['id']}.",reply_markup=InlineKeyboardMarkup(buttons))
        elif kind=='setstatus':
            listing_id,status=value.split(':',1)
            if status not in STATUSES:
                raise ValueError('Неверный статус')
            await asyncio.to_thread(in_db,lambda db:edit_owned(db,update.effective_user.id,int(listing_id),ListingUpdate(status=status)))
            await update.effective_message.reply_text(f'Статус: {STATUSES[status]}. Изменение сохранено в локальном каталоге.',reply_markup=MENU)
    except (LinkError,LookupError,ValueError) as exc:
        await update.effective_message.reply_text(str(exc),reply_markup=MENU)
