from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from Database.models import User


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.scalars(select(User).where(User.username == username)).first()


def insert_user(db: Session, username: str, password: str) -> bool:
    new_user = User(
        username=username,
        password=password
    )
    try:
        db.add(new_user)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(e)
        return False
