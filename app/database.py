"""Async SQLAlchemy engine, session factory and schema bootstrap."""

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for every ORM model in this service."""


_settings = get_settings()
engine = create_async_engine(_settings.database_url, future=True, echo=False)
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _ensure_sqlite_directory(database_url: str) -> None:
    """Create the folder holding the SQLite file, if the URL points at one."""
    marker = "sqlite+aiosqlite:///"
    if not database_url.startswith(marker):
        return
    file_path = Path(database_url[len(marker) :])
    if file_path.parent and str(file_path.parent) not in ("", "."):
        file_path.parent.mkdir(parents=True, exist_ok=True)


async def init_database() -> None:
    """Create the schema on startup.

    Same trade-off as the budget service: a single table and no schema evolution
    in scope. Production would version the schema with Alembic.
    """
    from app.models import subscription  # noqa: F401 - registra o modelo no metadata

    _ensure_sqlite_directory(_settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session."""
    async with SessionFactory() as session:
        yield session
