from collections.abc import Iterator
from datetime import UTC, datetime
from sqlite3 import Connection as SQLiteConnection
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import DateTime, Engine, create_engine, event
from sqlalchemy.engine import Dialect, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator


def make_engine(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return create_engine(parsed, pool_pre_ping=True)
    if parsed.database in (None, "", ":memory:"):
        engine = create_engine(
            parsed, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    else:
        engine = create_engine(parsed, connect_args={"timeout": 10})

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection: SQLiteConnection, _: object) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return engine


def as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=False)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return as_utc(value).replace(tzinfo=None) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return as_utc(value) if value is not None else None


def get_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


DB = Annotated[Session, Depends(get_session)]
