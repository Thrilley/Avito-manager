from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.core.security import current_user
from app.models import User, SourceAccount, SyncRun

router = APIRouter(prefix='/api/v1/sources', tags=['sources'])

class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    platform: str
    account_id: str

@router.get('', response_model=list[SourceResponse])
def sources(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return db.scalars(select(SourceAccount).where(SourceAccount.owner_id == user.id)).all()

@router.get('/{source_id}/runs')
def runs(source_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if db.scalar(select(SourceAccount.id).where(SourceAccount.id == source_id, SourceAccount.owner_id == user.id)) is None:
        raise HTTPException(404, 'Source not found')
    rows = db.scalars(select(SyncRun).where(SyncRun.source_id == source_id).order_by(SyncRun.id.desc()).limit(20))
    return [dict(id=r.id, status=r.status, started_at=r.started_at, finished_at=r.finished_at, imported=r.imported, error_code=r.error_code) for r in rows]

@router.post('/{source_id}/sync')
def sync(source_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if db.scalar(select(SourceAccount.id).where(SourceAccount.id == source_id, SourceAccount.owner_id == user.id)) is None:
        raise HTTPException(404, 'Source not found')
    raise HTTPException(503, 'Avito adapter awaits verified API documentation and account permissions')
