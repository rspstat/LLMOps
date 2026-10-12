import re
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_CLIENT_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestIdMiddleware:
    """Give every request a server-generated ID and return it in the `X-Request-ID` header.

    The ID is the trace primary key, so it is never taken from the client: a repeated or forged
    value would collide with, or pollute, another request's trace. A short URL-safe client
    `X-Request-ID` is kept separately as `client_request_id` for correlation.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        supplied = dict(scope["headers"]).get(REQUEST_ID_HEADER.lower().encode(), b"").decode()
        state["client_request_id"] = supplied if _VALID_CLIENT_ID.match(supplied) else None

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_with_header)
