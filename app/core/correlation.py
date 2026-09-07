"""Request correlation, so a single call can be traced across both services."""

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger("app.request")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Correlation id of the request currently being handled, if any."""
    return _request_id.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Reuse the caller's correlation id, or mint one when the call starts here.

    Also logs one line per request carrying that id, which is what makes a single
    call traceable across the two services rather than merely tagged.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        token = _request_id.set(request_id)
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
        finally:
            _request_id.reset(token)

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "%s %s -> %s em %.1fms [request_id=%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
