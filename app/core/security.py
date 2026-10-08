import os
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.models import User

hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)
DUMMY_HASH = hasher.hash('dummy-password-for-timing-only')
ISSUER = 'avito-manager'
AUDIENCE = 'avito-manager-api'

def signing_key():
    key = os.getenv('JWT_SECRET', '')
    if len(key.encode()) < 32:
        raise HTTPException(503, 'JWT_SECRET must be configured locally (at least 32 bytes)')
    return key

def verify_password(password, hashed):
    try:
        return hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False

def create_token(user_id):
    now = datetime.now(timezone.utc)
    return jwt.encode(dict(sub=str(user_id), iat=now, exp=now+timedelta(minutes=30), iss=ISSUER, aud=AUDIENCE), signing_key(), algorithm='HS256')

def unauthorized():
    return HTTPException(401, 'Invalid or missing credentials', headers={'WWW-Authenticate': 'Bearer'})

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if credentials is None:
        raise unauthorized()
    try:
        payload = jwt.decode(credentials.credentials, signing_key(), algorithms=['HS256'], issuer=ISSUER, audience=AUDIENCE, options={'require': ['sub', 'iat', 'exp', 'iss', 'aud']})
        user_id = int(payload['sub'])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise unauthorized()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return user

def require_admin(user: User = Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, 'Administrator access required')
    return user
