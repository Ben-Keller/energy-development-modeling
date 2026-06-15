"""Per-request context propagated via contextvars.

FastAPI's dependency injection works through parameter defaults, but some
helpers (e.g. get_db_session) want to read the current request without
threading it through every call site. Contextvars provide a clean way
to stash the active request for the duration of a handler invocation.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

try:
    from fastapi import Request  # type: ignore
except ImportError:  # pragma: no cover
    Request = None  # type: ignore


_current_request: ContextVar[Optional["Request"]] = ContextVar("edim_current_request", default=None)


def set_current_request(request: Optional["Request"]) -> object:
    """Bind a request to the current async context. Returns a token usable
    with reset_current_request to restore the prior value (call from a
    finally block to handle exceptions).
    """
    return _current_request.set(request)


def get_current_request() -> Optional["Request"]:
    return _current_request.get()


def reset_current_request(token: object) -> None:
    _current_request.reset(token)
