from __future__ import annotations

import os
from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = "postgresql+psycopg://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"


def database_url() -> str:
    return os.getenv("SL_LEGAL_DATABASE_URL") or os.getenv("SL_LEGAL_POSTGRES_DSN") or DEFAULT_DATABASE_URL


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), future=True, pool_pre_ping=True)


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or make_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Open a transaction-scoped SQLAlchemy session."""

    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_health(engine: Engine | None = None) -> dict[str, str | int]:
    active_engine = engine or make_engine()
    with active_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                WITH tables AS (
                    SELECT count(*) AS table_count
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ),
                indexes AS (
                    SELECT count(*) AS index_count
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                )
                SELECT
                    current_database() AS database_name,
                    (SELECT table_count FROM tables) AS table_count,
                    (SELECT index_count FROM indexes) AS index_count,
                    COALESCE(
                        (SELECT string_agg(version, ', ' ORDER BY version) FROM schema_migrations),
                        ''
                    ) AS migrations
                """
            )
        ).mappings().one()
    return {
        "database_name": str(row["database_name"]),
        "table_count": int(row["table_count"]),
        "index_count": int(row["index_count"]),
        "migrations": str(row["migrations"]),
    }
