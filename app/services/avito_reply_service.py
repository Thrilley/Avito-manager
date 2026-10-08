import re
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import AvitoChat, AvitoMessage, AvitoReply, SourceAccount
from app.integrations.gpt_replies import GenerationUnavailable

HANDOFF_TEXT = 'Передаю ваш запрос оператору. Он ответит вам в этом чате.'

# Conservative local trigger, available even when GPT is disabled.
# GPT can recognize additional phrasings once connected.
def requests_operator(text):
    text = text.lower().replace('ё', 'е')
    if re.search(r'не\s+(?:нужен|нужна|надо|хочу).*?(?:оператор|менеджер|человек)', text):
        return False
    return bool(re.search(
        r'(?:позовите|позови|вызовите|пригласите|подключите|дайте|нужен|нужна)\s+(?:мне\s+)?(?:живой\s+|живого\s+)?(?:оператор|менеджер|человек|продавец|продавца)'
        r'|(?:соедините|свяжите|переключите|поговорить|общаться|связаться).*?\b(?:с\s+)?(?:оператором|менеджером|человеком|продавцом)'
        r'|^(?:оператор|менеджер)[.!?\s]*$', text))

class ReplyConflict(Exception):
    pass

def owned_chat(db, owner_id, chat_id):
    chat = db.scalar(select(AvitoChat).join(SourceAccount).where(
        AvitoChat.id == chat_id, SourceAccount.owner_id == owner_id, SourceAccount.platform == 'avito'))
    if chat is None:
        raise LookupError('Chat not found')
    return chat

def ingest(db, owner_id, source_id, event):
    source = db.scalar(select(SourceAccount).where(SourceAccount.id == source_id,
        SourceAccount.owner_id == owner_id, SourceAccount.platform == 'avito'))
    if source is None:
        raise LookupError('Source not found')
    chat = db.scalar(select(AvitoChat).where(AvitoChat.source_id == source_id,
                                            AvitoChat.external_id == event.chat_id))
    if chat is None:
        chat = AvitoChat(source_id=source_id, external_id=event.chat_id)
        db.add(chat)
    try:
        db.flush()
        existing = db.scalar(select(AvitoMessage).where(AvitoMessage.chat_id == chat.id,
                                                       AvitoMessage.external_id == event.message_id))
        if existing:
            if (existing.text, existing.direction) != (event.text, event.direction):
                raise ReplyConflict('Message ID reused with different content')
            return existing
        message = AvitoMessage(chat_id=chat.id, external_id=event.message_id,
                               direction=event.direction, text=event.text)
        db.add(message)
        # Any seller message conservatively hands control back to the owner.
        if event.direction == 'out':
            chat.enabled = False
        db.flush()
        if event.direction == 'in' and requests_operator(event.text):
            chat.enabled, chat.human_required = False, True
            db.add(AvitoReply(chat_id=chat.id, message_id=message.id,
                              status='human_required', text=HANDOFF_TEXT))
        db.commit()
        return message
    except IntegrityError:
        db.rollback()
        raise ReplyConflict('Concurrent ingestion; retry the same event') from None

def generate(db, owner_id, message_id, generator):
    message = db.get(AvitoMessage, message_id)
    if message is None:
        raise LookupError('Message not found')
    chat = owned_chat(db, owner_id, message.chat_id)
    existing = db.scalar(select(AvitoReply).where(AvitoReply.message_id == message_id))
    if existing:
        return existing
    if not chat.enabled or chat.human_required or message.direction != 'in':
        raise ReplyConflict('Chat is paused or requires the owner')
    latest = db.scalar(select(AvitoMessage.id).where(AvitoMessage.chat_id == chat.id)
                       .order_by(AvitoMessage.id.desc()).limit(1))
    if latest != message.id:
        raise ReplyConflict('Only the latest message may receive a draft')
    reply = AvitoReply(chat_id=chat.id, message_id=message.id, status='generating')
    db.add(reply)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ReplyConflict('Generation already in progress') from None
    rows = list(db.scalars(select(AvitoMessage).where(AvitoMessage.chat_id == chat.id,
        AvitoMessage.id <= message.id).order_by(AvitoMessage.id.desc()).limit(12)))
    history = [{'role': 'user' if row.direction == 'in' else 'assistant', 'content': row.text}
               for row in reversed(rows)]
    try:
        draft = generator.generate(history)
    except Exception:
        reply.status, reply.error_code = 'failed', 'generation_unavailable'
        db.commit()
        raise GenerationUnavailable('GPT generation unavailable; inspect local configuration') from None
    db.refresh(chat)
    latest = db.scalar(select(AvitoMessage.id).where(AvitoMessage.chat_id == chat.id)
                       .order_by(AvitoMessage.id.desc()).limit(1))
    if not chat.enabled or chat.human_required or latest != message.id:
        reply.status = 'superseded'
    else:
        reply.text = draft.reply
        reply.status = 'human_required' if draft.human_required else 'draft'
        if draft.human_required:
            chat.human_required, chat.enabled = True, False
    db.commit()
    return reply
