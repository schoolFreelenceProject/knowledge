from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import Base


@lru_cache
def get_database_engine():
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_database_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


def init_db() -> None:
    settings = get_settings()
    if not settings.database_auto_create:
        return

    Base.metadata.create_all(bind=get_database_engine())
