from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apr_backend.core.settings import get_settings


def create_database_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


def get_db():
    with SessionLocal() as session:
        yield session
