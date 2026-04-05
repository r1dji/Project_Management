from datetime import datetime, timedelta
import jwt
from zoneinfo import ZoneInfo

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import Depends, HTTPException

from http import HTTPStatus

from sqlalchemy.orm import Session

from Database.models import User
from Database.db import get_db

from Services.users_service import get_user_by_username

from pwdlib import PasswordHash

from config import settings

password_hasher = PasswordHash.recommended()

TOKEN_DURATION = settings.JWT_TOKEN_DURATION_MINUTES
SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM

security = HTTPBearer()


def create_access_token(user: User) -> str:
    expire = datetime.now(ZoneInfo('Europe/Belgrade')) + timedelta(minutes=TOKEN_DURATION)

    payload = {
        'user': user.username,
        'user_id': user.user_id,
        'exp': expire
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail="Invalid token")

    username = payload.get("user")
    if not username:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail="Invalid token payload")

    user = get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail="User not found")

    return user
