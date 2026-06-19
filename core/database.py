"""SQLAlchemy database setup with sync compatibility and async support."""

from __future__ import annotations

import importlib.util
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


Base = declarative_base()


def _async_database_url(database_url: str) -> str:
    url = make_url(database_url)
    driver = url.drivername
    if driver.startswith("sqlite"):
        return str(url.set(drivername="sqlite+aiosqlite"))
    if driver in {"postgresql", "postgres"} or driver.startswith("postgresql+"):
        return str(url.set(drivername="postgresql+asyncpg"))
    return database_url


def _sync_database_url(database_url: str) -> str:
    url = make_url(database_url)
    driver = url.drivername
    if driver == "sqlite+aiosqlite":
        return str(url.set(drivername="sqlite"))
    if driver == "postgresql+asyncpg":
        if importlib.util.find_spec("psycopg"):
            return str(url.set(drivername="postgresql+psycopg"))
        return str(url.set(drivername="postgresql"))
    return database_url


SYNC_DATABASE_URL = _sync_database_url(settings.DATABASE_URL)
ASYNC_DATABASE_URL = _async_database_url(settings.DATABASE_URL)

connect_args = {}
if SYNC_DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    SYNC_DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=not SYNC_DATABASE_URL.startswith("sqlite"),
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

async_engine = None
AsyncSessionLocal = None
_async_driver = make_url(ASYNC_DATABASE_URL).drivername.split("+")[-1]
if importlib.util.find_spec(_async_driver):
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        pool_pre_ping=not ASYNC_DATABASE_URL.startswith("sqlite"),
        echo=False,
        future=True,
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def get_db() -> Generator:
    """FastAPI dependency for existing synchronous modules."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _import_model_modules() -> None:
    """Register all SQLAlchemy models on Base.metadata before create_all."""
    import core.models  # noqa: F401
    import modules.metadata.models  # noqa: F401


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for new async-ready routes."""
    if AsyncSessionLocal is None:
        raise RuntimeError(
            f"Async database driver for {ASYNC_DATABASE_URL!r} is not installed. "
            "Install requirements.txt to enable async database sessions."
        )
    async with AsyncSessionLocal() as db:
        yield db


def _column_type_sql(column) -> str:
    name = column.type.__class__.__name__.lower()
    if "integer" in name:
        return "INTEGER"
    if "boolean" in name:
        return "BOOLEAN"
    if "float" in name or "numeric" in name:
        return "FLOAT"
    if "datetime" in name:
        return "DATETIME"
    if "json" in name:
        return "JSON"
    if "text" in name:
        return "TEXT"
    return "VARCHAR"


def _ensure_additive_columns() -> None:
    """Add newly introduced columns for old local SQLite databases.

    This is an MVP local-dev bridge only. Production schema changes should use
    Alembic migrations.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    dialect = engine.dialect.name
    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue

        existing = {col["name"] for col in inspector.get_columns(table_name)}
        missing = [column for column in table.columns if column.name not in existing]
        if not missing:
            continue

        with engine.begin() as conn:
            for column in missing:
                col_type = _column_type_sql(column)
                if dialect == "postgresql" and col_type == "JSON":
                    col_type = "JSONB"
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}"))


def init_db() -> None:
    """Create tables and lightly migrate additive history fields."""
    _import_model_modules()
    Base.metadata.create_all(bind=engine)
    _ensure_additive_columns()
