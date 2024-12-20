from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models.base_model import Base
import os

load_dotenv()

# echo = True to see the SQL queries
engine = create_engine(os.getenv("DB_URL"), echo=True)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    with Session(engine) as session:
        yield session