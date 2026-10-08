import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update, delete, exists, or_
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, ConfigDict, Field, model_validator
from decimal import Decimal
from typing import Literal
from app.models import User, Listing, ExternalListing, TelegramLinkCode, TelegramBinding
from app.shemas import ListingResponse

class LinkError(Exception):
    pass

class CatalogFilter(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    q: str | None = Field(default=None, min_length=1, max_length=250)
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    size: str | None = Field(default=None, min_length=1, max_length=30)
    condition: Literal['new','used'] | None = None
    price_min: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    price_max: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def price_range(self):
        if self.price_min is not None and self.price_max is not None and self.price_min > self.price_max:
            raise ValueError('Invalid price range')
        return self

def issue_code(db, owner_id):
    now = datetime.now(timezone.utc)
    # One current code per owner, not a permanent API credential.
    db.execute(update(TelegramLinkCode).where(TelegramLinkCode.owner_id == owner_id, TelegramLinkCode.used_at.is_(None)).values(used_at=now))
    code = secrets.token_urlsafe(24)
    db.add(TelegramLinkCode(owner_id=owner_id, code_hash=hashlib.sha256(code.encode()).hexdigest(), expires_at=now+timedelta(minutes=10)))
    db.commit()
    return code

def consume_code(db, telegram_id, code):
    if telegram_id <= 0 or not 20 <= len(code) <= 100:
        raise LinkError('Invalid code')
    now = datetime.now(timezone.utc)
    owner = db.execute(update(TelegramLinkCode).where(TelegramLinkCode.code_hash == hashlib.sha256(code.encode()).hexdigest(), TelegramLinkCode.used_at.is_(None), TelegramLinkCode.expires_at > now).values(used_at=now).returning(TelegramLinkCode.owner_id)).scalar_one_or_none()
    if owner is None:
        db.rollback()
        raise LinkError('Code expired or already used')
    user = db.get(User, owner)
    if user is None or not user.is_active:
        db.rollback()
        raise LinkError('Account unavailable')
    db.add(TelegramBinding(telegram_id=telegram_id, owner_id=owner))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise LinkError('Account already linked; unlink it through the API first')
    return owner

def unlink(db, owner_id):
    db.execute(delete(TelegramBinding).where(TelegramBinding.owner_id == owner_id))
    db.execute(update(TelegramLinkCode).where(TelegramLinkCode.owner_id == owner_id, TelegramLinkCode.used_at.is_(None)).values(used_at=datetime.now(timezone.utc)))
    db.commit()

def linked_owner(db, telegram_id):
    owner = db.scalar(select(User.id).join(TelegramBinding, TelegramBinding.owner_id == User.id).where(TelegramBinding.telegram_id == telegram_id, User.is_active.is_(True)))
    if owner is None:
        raise LinkError('Сначала привяжи аккаунт: /link КОД')
    return owner

def available_query(owner_id):
    # A missing/unknown/closed external source must not appear as available.
    unavailable = exists(select(ExternalListing.id).where(ExternalListing.listing_id == Listing.id, or_(ExternalListing.source_present.is_(False), ExternalListing.source_data.is_(None), ExternalListing.source_data['catalog_status'].as_string().is_(None), ExternalListing.source_data['catalog_status'].as_string() != 'active')))
    return select(Listing).where(Listing.owner_id == owner_id, Listing.status == 'active', ~unavailable)

def catalog_page(db, telegram_id, filters, page=0):
    if not 0 <= page <= 10000:
        raise ValueError('Invalid page')
    query = available_query(linked_owner(db, telegram_id))
    if filters.q:
        pattern = '%' + filters.q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
        query = query.where(or_(Listing.title.ilike(pattern, escape='\\'), Listing.description.ilike(pattern, escape='\\')))
    for field in ['brand','size','condition']:
        value = getattr(filters,field)
        if value is not None:
            query = query.where(getattr(Listing,field) == value)
    if filters.price_min is not None:
        query = query.where(Listing.price >= filters.price_min)
    if filters.price_max is not None:
        query = query.where(Listing.price <= filters.price_max)
    rows = db.scalars(query.order_by(Listing.id.desc()).offset(page*5).limit(6)).all()
    return [ListingResponse.model_validate(row).model_dump(mode='json') for row in rows[:5]], len(rows)>5

def item_card(db, telegram_id, listing_id):
    row = db.scalar(available_query(linked_owner(db,telegram_id)).where(Listing.id == listing_id))
    if row is None:
        raise LookupError('Товар недоступен')
    return ListingResponse.model_validate(row).model_dump(mode='json')

def owned_item(db, telegram_id, listing_id):
    owner=linked_owner(db,telegram_id)
    row=db.scalar(select(Listing).where(Listing.id==listing_id,Listing.owner_id==owner))
    if row is None:
        raise LookupError('Товар не найден')
    return ListingResponse.model_validate(row).model_dump(mode='json')

def owned_page(db, telegram_id, page=0):
    if not 0<=page<=10000:
        raise ValueError('Invalid page')
    owner=linked_owner(db,telegram_id)
    rows=db.scalars(select(Listing).where(Listing.owner_id==owner).order_by(Listing.id.desc()).offset(page*5).limit(6)).all()
    return [ListingResponse.model_validate(row).model_dump(mode='json') for row in rows[:5]],len(rows)>5

def edit_owned(db, telegram_id, listing_id, data):
    from app.services.listing_service import update_listing
    from fastapi import HTTPException
    owner=linked_owner(db,telegram_id)
    try:
        return update_listing(listing_id,data,db,owner_id=owner).id
    except HTTPException as exc:
        if exc.status_code==404:
            raise LookupError('Товар не найден') from exc
        raise
