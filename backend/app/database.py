import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite for local dev by default. Set DATABASE_URL env var to a Postgres
# connection string (e.g. postgresql://user:pass@host:5432/db) for deployment.
# SQLAlchemy's URL abstraction means no other code needs to change.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ethara.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
