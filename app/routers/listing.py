from fastapi import APIRouter, Depends
from app.shemas import ListingCreate, ListingResponse, ListingUpdate, ListingUpdateStatus, ListingStatus
from app.dependencies import get_db
from app.core.security import current_user
from app.models import User
from app.services.listing_service import(
    create_listing,
    get_listing,
    get_listing_by_id,
    update_listing,
    delete_listing,
    change_listing_status,
    filter_listing,
    search_listing,
    sort_listing
)
from typing import List
router = APIRouter()

@router.post("/listings", response_model=ListingResponse)
def end_create_listing(data: ListingCreate, db = Depends(get_db), user: User = Depends(current_user)):
    listing = create_listing(data, db, owner_id=user.id)
    return listing

@router.get("/listings", response_model=List[ListingResponse])
def end_get_listing(db = Depends(get_db), user: User = Depends(current_user)):
    lisitng = get_listing(db, owner_id=user.id)
    return lisitng

@router.get("/listings/{listing_id}")
def get_by_id(listing_id: int, db = Depends(get_db), user: User = Depends(current_user)):
    lisiting = get_listing_by_id(listing_id, db, owner_id=user.id)
    return lisiting

@router.patch("/listing/{listing_id}",response_model=ListingResponse)
def end_update_listing(listing_id: int, data: ListingUpdate, db = Depends(get_db), user: User = Depends(current_user)):
    listing = update_listing(listing_id, data, db, owner_id=user.id)
    return listing

@router.delete("/listing/{listing_id}")
def end_delete_listing(listing_id: int, db = Depends(get_db), user: User = Depends(current_user)):
    listing = delete_listing(listing_id, db, owner_id=user.id)
    return listing

@router.patch("/listing/staty/{listing_id}", response_model=ListingResponse)
def update_status(listing_id: int, status: ListingStatus,  db = Depends(get_db), user: User = Depends(current_user)):
    listing = change_listing_status(listing_id, status, db, owner_id=user.id)
    return listing


@router.get("/listing/search")
def listing_search(search: str, db = Depends(get_db), user: User = Depends(current_user)):
    listing = search_listing(search, db, owner_id=user.id)
    return listing




@router.get("/listing/filter")
def filter_listing_search(
    status: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    db = Depends(get_db), user: User = Depends(current_user)):
    listing = filter_listing(status, min_price, max_price, db, owner_id=user.id)
    return listing

@router.get("/listing/sort")
def listing_sort(sort: str, sort_plan: str, db = Depends(get_db), user: User = Depends(current_user)):
    listing = sort_listing(db, sort, sort_plan, owner_id=user.id)
    return listing
