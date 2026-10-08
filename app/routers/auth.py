from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.models import User
from app.core.security import hasher, verify_password, DUMMY_HASH, create_token, current_user, unauthorized

router = APIRouter(prefix='/api/v1/auth', tags=['auth'])

class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=100, pattern=r'^[A-Za-z0-9_.-]+$')
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator('username')
    @classmethod
    def normalize(cls, value):
        return value.lower()

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    is_admin: bool

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_in: int = 1800

@router.post('/register', response_model=UserResponse, status_code=201)
def register(data: Credentials, db: Session = Depends(get_db)):
    user = User(username=data.username, password_hash=hasher.hash(data.password.get_secret_value()))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Username unavailable')
    return user

@router.post('/login', response_model=TokenResponse)
def login(data: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == data.username))
    valid = verify_password(data.password.get_secret_value(), user.password_hash if user else DUMMY_HASH)
    if not valid or user is None or not user.is_active:
        raise unauthorized()
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(data.password.get_secret_value())
        db.commit()
    return TokenResponse(access_token=create_token(user.id))

@router.get('/me', response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return user

from app.core.security import require_admin

@router.get('/users', response_model=list[UserResponse])
def users(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.scalars(select(User).order_by(User.id).offset(offset).limit(limit)).all()
