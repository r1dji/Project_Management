from datetime import datetime, timedelta
from http import HTTPStatus
from zoneinfo import ZoneInfo

import jwt
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from Database.db import get_db
from Database.models import User
from Schemas.auth_schemas import SignUpRequest, LoginRequest
from Services.users_service import get_user_by_username, insert_user
from config import settings

router = APIRouter(tags=['Auth'])

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
):
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


@router.post('/auth')
def sign_up(data: SignUpRequest, db: Session = Depends(get_db)):
    if data.password != data.repeated_password:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Passwords do not match')

    existing_user = get_user_by_username(db, data.username)
    if existing_user:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Username already exists')

    hashed_password = password_hasher.hash(data.password)

    if insert_user(db, data.username, hashed_password):
        return JSONResponse(
            content={'message': 'User created successfully'},
            status_code=HTTPStatus.CREATED
        )
    else:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to create user')


@router.post('/login')
def login(data: LoginRequest, db: Session = Depends(get_db)):
    username = data.username
    password = data.password

    if not username:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Username is required')
    elif not password:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Password is required')

    user = get_user_by_username(db, username)

    if not user:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail='Invalid username')

    if not password_hasher.verify(password, user.password):
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail='Passwords does not match')

    access_token = create_access_token(user)

    return JSONResponse(
        content={
            'message': 'Login successful',
            'access_token': access_token
        },
        status_code=HTTPStatus.OK
    )
