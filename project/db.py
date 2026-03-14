from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base

# connection to db parameters
user = 'postgres'
password = 'postgres'
host = 'localhost'
port = 5432
db_name = 'project_management'

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
