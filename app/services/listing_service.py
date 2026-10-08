from app.database import SessionLocal
from app.shemas import ListingCreate, ListingResponse, ListingUpdate
from app.models import Listing
from sqlalchemy import select, or_
from fastapi import HTTPException



def create_listing(data: ListingCreate, db, owner_id=None):


    new_listing = Listing(**data.model_dump(), owner_id=owner_id)
    db.add(new_listing)
    db.commit()
    return new_listing

def get_listing(db, owner_id=None):
    result = db.execute(
    select(Listing).where(Listing.owner_id == owner_id)
    )
    listing = result.scalars().all()
    return listing

def get_listing_by_id(listing_id: int, db, owner_id=None):
    result = db.execute(
        select(Listing).where(Listing.id == listing_id, Listing.owner_id == owner_id)
    )
    listing = result.scalar_one_or_none()
    if listing is None:
             raise HTTPException(404)

    return listing

def update_listing(listing_id: int, data: ListingUpdate, db, owner_id=None):
    result = db.execute(
        select(Listing).where(Listing.id == listing_id, Listing.owner_id == owner_id)
    )
    listing_one = result.scalar_one_or_none()
    if listing_one is None:
            raise HTTPException(404)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(listing_one, field, value)
    db.commit()
    return listing_one

def delete_listing(listing_id: int, db, owner_id=None):
      search_listing = db.execute(
        select(Listing).where(Listing.id == listing_id, Listing.owner_id == owner_id)
      )
      listing = search_listing.scalar_one_or_none()
      if listing is None:
            raise HTTPException(404)
      db.delete(listing)
      db.commit()
      return listing

def change_listing_status(lisitng_id: int, status: str, db, owner_id=None):
      search_listing = db.execute(
            select(Listing).where(Listing.id == lisitng_id, Listing.owner_id == owner_id)
      )
      listing = search_listing.scalar_one_or_none()
      if listing is None:
            raise HTTPException(404)
      listing.status = status
      db.commit()
      return listing

def search_listing(search, db, owner_id=None):
      search_listing = db.execute(
            select(Listing).where(Listing.owner_id == owner_id).where(or_(Listing.title.ilike(f"%{search}%"),
             Listing.description.ilike(f"%{search}%")))
            )
      listing = search_listing.scalars().all()
      return listing

def filter_listing(status, min_price, max_price, db, owner_id=None):
      query = select(Listing).where(Listing.owner_id == owner_id)
      if status is not None:
            query = query.where(Listing.status == status)

      if min_price is not None:
            query = query.where(Listing.price >= min_price)
      if max_price is not None:
            query = query.where(Listing.price <= max_price)
      listing_request = db.execute(query)
      lisiting = listing_request.scalars().all()
      return lisiting

def sort_listing(db, sort, sort_plan, owner_id=None):
    query = select(Listing).where(Listing.owner_id == owner_id)

    if sort == "title":
        sort_field = Listing.title
    elif sort == "description":
        sort_field = Listing.description
    elif sort == "price":
        sort_field = Listing.price
    elif sort == "created_at":
        sort_field = Listing.created_at
    elif sort == "status":
        sort_field = Listing.status
    else:
        raise HTTPException(status_code=400, detail="Invalid sort field")

    if sort_plan == "asc":
        plan_field = sort_field.asc()
    elif sort_plan == "desc":
        plan_field = sort_field.desc()
    else:
        raise HTTPException(status_code=400, detail="Invalid sort plan")

    listing_field = query.order_by(plan_field)
    listing = db.scalars(listing_field).all()

    return listing
