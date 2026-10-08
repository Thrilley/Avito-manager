from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from app.models import Listing, User
from app.core.security import current_user
from app.shemas import ListingCreate, ListingResponse, ListingUpdate, ListingUpdateStatus, ListingStatus, Condition
from app.dependencies import get_db
from app.services.listing_service import create_listing, get_listing_by_id, update_listing, delete_listing, change_listing_status

router = APIRouter(prefix='/api/v1/listings', tags=['catalog'])

@router.get('', response_model=list[ListingResponse])
def catalog(q: str | None = Query(None, min_length=1, max_length=250),
            brand: str | None = None, size: str | None = None,
            condition: Condition | None = None, status: ListingStatus | None = None,
            price_min: Decimal | None = Query(None, ge=0), price_max: Decimal | None = Query(None, ge=0),
            sort: Literal['created_at', 'price', 'title'] = 'created_at',
            order: Literal['asc', 'desc'] = 'desc',
            limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db), user: User = Depends(current_user)):
    if price_min is not None and price_max is not None and price_min > price_max:
        raise HTTPException(422, 'price_min must not exceed price_max')
    query = select(Listing).where(Listing.owner_id == user.id)
    if q:
        pattern = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.where(or_(Listing.title.ilike(pattern, escape='\\'), Listing.description.ilike(pattern, escape='\\')))
    for field, value in [('brand', brand), ('size', size), ('condition', condition), ('status', status)]:
        if value is not None:
            query = query.where(getattr(Listing, field) == value)
    if price_min is not None:
        query = query.where(Listing.price >= price_min)
    if price_max is not None:
        query = query.where(Listing.price <= price_max)
    column = getattr(Listing, sort)
    query = query.order_by(column.asc() if order == 'asc' else column.desc(), Listing.id.asc())
    return db.scalars(query.offset(offset).limit(limit)).all()

@router.post('', response_model=ListingResponse, status_code=201)
def create(data: ListingCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return create_listing(data, db, owner_id=user.id)

@router.get('/{listing_id}', response_model=ListingResponse)
def get(listing_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return get_listing_by_id(listing_id, db, owner_id=user.id)

@router.patch('/{listing_id}', response_model=ListingResponse)
def update(listing_id: int, data: ListingUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return update_listing(listing_id, data, db, owner_id=user.id)

@router.patch('/{listing_id}/status', response_model=ListingResponse)
def status_update(listing_id: int, data: ListingUpdateStatus, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return change_listing_status(listing_id, data.status, db, owner_id=user.id)

@router.delete('/{listing_id}', status_code=204)
def delete(listing_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    delete_listing(listing_id, db, owner_id=user.id)
