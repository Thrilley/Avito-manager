from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, UniqueConstraint, Boolean, true as sa_true, false as sa_false, Index, JSON, BigInteger
from .database import Base

def utcnow():
    return datetime.now(timezone.utc)

class Listing(Base):
    __tablename__ = 'listing'
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    status = Column(String, nullable=False)
    brand = Column(String(100))
    size = Column(String(30))
    condition = Column(String(30))
    owner_id = Column(Integer, ForeignKey('users.id'), index=True)
    currency = Column(String(3), nullable=False, default='RUB', server_default='RUB')

class ExternalListing(Base):
    __tablename__ = 'external_listing'
    __table_args__ = (UniqueConstraint('platform', 'account_id', 'external_id', name='uq_external_identity'),)
    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey('listing.id', ondelete='CASCADE'), nullable=False, index=True)
    platform = Column(String(30), nullable=False)
    account_id = Column(String(100), nullable=False)
    external_id = Column(String(100), nullable=False)
    url = Column(String(2048))
    external_status = Column(String(100))
    source_present = Column(Boolean, nullable=False, default=True, server_default=sa_true())
    source_data = Column(JSON)
    synced_at = Column(DateTime(timezone=True))

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(512), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=sa_true())
    is_admin = Column(Boolean, nullable=False, default=False, server_default=sa_false())
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class SourceAccount(Base):
    __tablename__ = 'source_account'
    __table_args__ = (UniqueConstraint('platform', 'account_id', name='uq_source_account'),)
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    platform = Column(String(30), nullable=False)
    account_id = Column(String(100), nullable=False)

class SyncRun(Base):
    __tablename__ = 'sync_run'
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey('source_account.id'), nullable=False)
    status = Column(String(30), nullable=False)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at = Column(DateTime(timezone=True))
    error_code = Column(String(50))
    imported = Column(Integer, nullable=False, default=0, server_default='0')

Index('uq_running_sync', SyncRun.source_id, unique=True,
      sqlite_where=SyncRun.status == 'running', postgresql_where=SyncRun.status == 'running')

class TelegramLinkCode(Base):
    __tablename__ = 'telegram_link_code'
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    code_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True))

class TelegramBinding(Base):
    __tablename__ = 'telegram_binding'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, unique=True)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True)

class AvitoChat(Base):
    __tablename__ = 'avito_chat'
    __table_args__ = (UniqueConstraint('source_id', 'external_id', name='uq_avito_chat'),)
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey('source_account.id'), nullable=False)
    external_id = Column(String(100), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False, server_default=sa_false())
    human_required = Column(Boolean, nullable=False, default=False, server_default=sa_false())

class AvitoMessage(Base):
    __tablename__ = 'avito_message'
    __table_args__ = (UniqueConstraint('chat_id', 'external_id', name='uq_avito_message'),)
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('avito_chat.id'), nullable=False)
    external_id = Column(String(100), nullable=False)
    direction = Column(String(10), nullable=False)
    text = Column(String(4000), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class AvitoReply(Base):
    __tablename__ = 'avito_reply'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('avito_chat.id'), nullable=False)
    message_id = Column(Integer, ForeignKey('avito_message.id'), nullable=False, unique=True)
    status = Column(String(30), nullable=False)
    text = Column(String(2000))
    error_code = Column(String(50))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

Index('uq_avito_generating', AvitoReply.chat_id, unique=True,
      sqlite_where=AvitoReply.status == 'generating', postgresql_where=AvitoReply.status == 'generating')
