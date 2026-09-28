"""
app/core/database.py  –  HOW WE TALK TO THE DATABASE
======================================================
We use SQLAlchemy, an "ORM" (Object-Relational Mapper). Instead of writing SQL by hand,
each table is a Python class (see app/models/) and each row is a Python object.

    engine        = the actual connection to the database file / server
    SessionLocal  = a factory that gives us a "session" (a short conversation with the DB)
    Base          = the parent class every table-class inherits from
    get_db()      = a helper FastAPI calls for every request: open session → run endpoint → close session
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# SQLite normally refuses to be used from more than one thread; FastAPI uses several, so we allow it.
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Every model in app/models/ does `class Something(Base):` – that's how SQLAlchemy finds the tables."""


def get_db():
    """
    Used like this in every endpoint:   def my_endpoint(db: Session = Depends(get_db)):
    FastAPI runs the code before `yield` (open), hands `db` to the endpoint, then runs the
    code after `yield` (close) - even if the endpoint crashed.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
