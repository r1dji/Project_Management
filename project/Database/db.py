from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from Database.models import Base
from config import settings

# connection to db parameters
user = settings.DB_USER
password = settings.DB_PASSWORD
host = settings.DB_HOST
port = settings.DB_PORT
db_name = settings.DB_NAME

DATABASE_URL = f'postgresql+psycopg://{user}:{password}@{host}:{port}/{db_name}'

engine = create_engine(
    DATABASE_URL
)

session = sessionmaker(bind=engine)


def get_db():
    db = session()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
