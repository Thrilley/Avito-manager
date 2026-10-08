from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.core.security import current_user
from app.models import User
from app.services.telegram_service import issue_code, unlink

router = APIRouter(prefix='/api/v1/telegram', tags=['telegram'])

@router.post('/link-code')
def link_code(response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return dict(code=issue_code(db,user.id), expires_in=600)

@router.delete('/binding', status_code=204)
def remove_binding(db: Session = Depends(get_db), user: User = Depends(current_user)):
    unlink(db,user.id)
