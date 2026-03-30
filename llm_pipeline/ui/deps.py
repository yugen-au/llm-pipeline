"""Dependency injection for llm-pipeline UI routes."""
from typing import Annotated, Generator

from fastapi import Depends, Request
from sqlmodel import Session

from llm_pipeline.session.readonly import ReadOnlySession


def get_db(request: Request) -> Generator[ReadOnlySession, None, None]:
    """Yield a read-only database session.

    Creates a SQLModel Session from the app-level engine, wraps it in
    ReadOnlySession to prevent accidental writes via the API layer.

    Note: ReadOnlySession has no close() method, so the underlying
    Session is closed directly in the finally block.
    """
    engine = request.app.state.engine
    session = Session(engine)
    try:
        yield ReadOnlySession(session)
    finally:
        session.close()


DBSession = Annotated[ReadOnlySession, Depends(get_db)]


def get_writable_db(request: Request) -> Generator[Session, None, None]:
    """Yield a writable database session."""
    engine = request.app.state.engine
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


WritableDBSession = Annotated[Session, Depends(get_writable_db)]

__all__ = ["get_db", "DBSession", "get_writable_db", "WritableDBSession"]
