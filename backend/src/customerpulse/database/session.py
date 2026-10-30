"""Engine and session helpers. Engines are created lazily per URL."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from customerpulse.settings import get_settings, normalise_url


@lru_cache(maxsize=8)
def engine_for(url: str, serverless: bool = False) -> Engine:
    # NullPool suits short-lived serverless invocations behind Neon's pooler.
    kwargs = {"poolclass": NullPool} if serverless else {"pool_pre_ping": True, "pool_size": 5}
    return create_engine(normalise_url(url), **kwargs)


def reader_engine() -> Engine:
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return engine_for(url, serverless=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one read-only session per request."""
    factory = sessionmaker(bind=reader_engine(), autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session
