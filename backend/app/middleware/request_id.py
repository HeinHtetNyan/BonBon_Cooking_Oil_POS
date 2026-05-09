"""
Request ID middleware.

Assigns a unique UUID to every inbound request and propagates it through:
1. Request headers (X-Request-ID) — echoed back in the response
2. structlog context variables — appears in every log line for this request
3. Response headers — allows clients to correlate their logs with server logs

If the client sends X-Request-ID, that value is respected (useful for
distributed tracing from mobile/PWA clients).
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())

        # Bind to structlog context so all log lines in this request carry request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
