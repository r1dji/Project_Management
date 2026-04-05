from http import HTTPStatus

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from Database.db import get_db
from Schemas.auth_schemas import SignUpRequest, LoginRequest, LoginResponse
from Schemas.message_schemas import MessageResponse
from Services.users_service import get_user_by_username, insert_user

from Services.auth_service import create_access_token, password_hasher

router = APIRouter(tags=['Auth'])


@router.post('/auth', status_code=HTTPStatus.CREATED)
def sign_up(data: SignUpRequest, db: Session = Depends(get_db)) -> MessageResponse:
    if data.password != data.repeated_password:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Passwords do not match')

    existing_user = get_user_by_username(db, data.username)
    if existing_user:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Username already exists')

    hashed_password = password_hasher.hash(data.password)

    if insert_user(db, data.username, hashed_password):
        return MessageResponse(message='User created successfully')
    else:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to create user')


@router.post('/login', status_code=HTTPStatus.OK)
def login(data: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
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

    return LoginResponse(message="Login successfully", access_token=access_token)
