from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from cowcloak.mailcow import MailcowAccessDenied, MailcowError


class AccessRevalidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith("/aliases"):
            return await call_next(request)

        email = request.session.get("user_email")
        settings = request.app.state.settings
        if not email or not settings.access_tag:
            return await call_next(request)

        try:
            await request.app.state.mailcow.get_mailbox(str(email).lower())
        except MailcowAccessDenied:
            request.session.clear()
            return RedirectResponse("/?error=access-denied", status_code=303)
        except MailcowError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)

        return await call_next(request)
