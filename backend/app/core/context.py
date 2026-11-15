"""Per-request context (request id, client IP, user agent) for logs and the audit trail."""

import uuid
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.types import ASGIApp, Message, Receive, Scope, Send


@dataclass(frozen=True)
class RequestInfo:
    request_id: str
    ip: str | None
    user_agent: str | None


_current: ContextVar[RequestInfo | None] = ContextVar("request_info", default=None)


def current_request() -> RequestInfo | None:
    return _current.get()


class RequestContextMiddleware:
    """Pure ASGI middleware: stores request info and returns `X-Request-ID`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        # Behind Caddy the first X-Forwarded-For entry is the client.
        forwarded = headers.get("x-forwarded-for", "").split(",")[0].strip()
        client = scope.get("client")
        info = RequestInfo(
            request_id=str(uuid.uuid4()),
            ip=forwarded or (client[0] if client else None),
            user_agent=(headers.get("user-agent") or "")[:512] or None,
        )
        token = _current.set(info)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (b"x-request-id", info.request_id.encode())
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _current.reset(token)
