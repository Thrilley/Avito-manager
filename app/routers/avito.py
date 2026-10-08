"""Authenticated operator API, NOT a native/public Avito webhook."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.core.security import current_user
from app.models import User, SourceAccount, AvitoChat, AvitoMessage, AvitoReply
from app.integrations.gpt_replies import OpenAIReplies, GenerationUnavailable
from app.services.avito_reply_service import ingest, generate, owned_chat, ReplyConflict

router = APIRouter(prefix='/api/v1/avito', tags=['avito'], dependencies=[])

class Event(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    chat_id: str = Field(min_length=1, max_length=100)
    message_id: str = Field(min_length=1, max_length=100)
    direction: Literal['in', 'out']
    text: str = Field(min_length=1, max_length=4000)

class ChatSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool
    human_required: bool

def private(response: Response):
    response.headers['Cache-Control'] = 'no-store'

def result(reply):
    return dict(id=reply.id, message_id=reply.message_id, status=reply.status,
                text=reply.text, error_code=reply.error_code)

@router.post('/sources/{source_id}/events')
def event(source_id: int, body: Event, response: Response,
          db: Session = Depends(get_db), user: User = Depends(current_user)):
    private(response)
    try:
        row = ingest(db, user.id, source_id, body)
        return dict(id=row.id, chat_id=row.chat_id)
    except LookupError:
        raise HTTPException(404, 'Source not found') from None
    except ReplyConflict as exc:
        raise HTTPException(409, str(exc)) from None

@router.get('/chats')
def chats(response: Response, limit: int = Query(50, ge=1, le=100),
          offset: int = Query(0, ge=0), human_required: bool | None = None,
          db: Session = Depends(get_db), user: User = Depends(current_user)):
    private(response)
    query = select(AvitoChat).join(SourceAccount).where(
        SourceAccount.owner_id == user.id, SourceAccount.platform == 'avito')
    if human_required is not None:
        query = query.where(AvitoChat.human_required == human_required)
    rows = db.scalars(query.order_by(AvitoChat.id.desc()).limit(limit).offset(offset))
    return [dict(id=c.id, source_id=c.source_id, external_id=c.external_id,
                 enabled=c.enabled, human_required=c.human_required) for c in rows]

@router.patch('/chats/{chat_id}')
def settings(chat_id: int, body: ChatSettings, response: Response,
             db: Session = Depends(get_db), user: User = Depends(current_user)):
    private(response)
    try:
        chat = owned_chat(db, user.id, chat_id)
    except LookupError:
        raise HTTPException(404, 'Chat not found') from None
    if body.enabled and body.human_required:
        raise HTTPException(422, 'Resolve human handoff before enabling')
    chat.enabled, chat.human_required = body.enabled, body.human_required
    db.commit()
    return dict(id=chat.id, enabled=chat.enabled, human_required=chat.human_required)

@router.get('/chats/{chat_id}/messages')
def messages(chat_id: int, response: Response, limit: int = Query(50, ge=1, le=100),
             offset: int = Query(0, ge=0), db: Session = Depends(get_db), user: User = Depends(current_user)):
    private(response)
    try:
        owned_chat(db, user.id, chat_id)
    except LookupError:
        raise HTTPException(404, 'Chat not found') from None
    rows = db.scalars(select(AvitoMessage).where(AvitoMessage.chat_id == chat_id)
                      .order_by(AvitoMessage.id.desc()).limit(limit).offset(offset))
    return [dict(id=m.id, external_id=m.external_id, direction=m.direction, text=m.text,
                 reply=result(r) if (r := db.scalar(select(AvitoReply).where(
                     AvitoReply.message_id == m.id))) else None) for m in rows]

@router.post('/messages/{message_id}/draft')
def draft(message_id: int, response: Response, db: Session = Depends(get_db),
          user: User = Depends(current_user)):
    private(response)
    try:
        return result(generate(db, user.id, message_id, OpenAIReplies()))
    except LookupError:
        raise HTTPException(404, 'Message not found') from None
    except ReplyConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except GenerationUnavailable:
        raise HTTPException(503, 'GPT generation unavailable; check local configuration') from None
