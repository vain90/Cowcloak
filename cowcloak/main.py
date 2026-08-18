from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from cowcloak import __version__
from cowcloak.aliases import RESERVED_COMMENT, is_owned_alias, mailbox_domain, named_local_part, readable_local_part, validate_local_part
from cowcloak.auth import OAuthError, authorization_url, exchange_code, validate_oauth_state
from cowcloak.config import Settings, get_settings
from cowcloak.mailcow import MailcowClient, MailcowError
from cowcloak.security import ensure_csrf_token, require_user, validate_csrf

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.mailcow = MailcowClient(settings)
        yield
        await app.state.mailcow.close()

    app = FastAPI(title="Cowcloak", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, session_cookie="cowcloak_session", same_site="lax", https_only=settings.cookie_secure, max_age=60 * 60 * 12)
    if settings.trusted_host_list != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'"
        return response

    def client(request: Request) -> MailcowClient:
        return request.app.state.mailcow

    async def owned_alias(request: Request, alias_id: int):
        user = require_user(request)
        alias = await client(request).get_alias(alias_id)
        if not is_owned_alias(alias, user):
            raise HTTPException(status_code=403, detail="Alias is not owned by this mailbox")
        return user, alias

    async def create_unique_alias(request: Request, user: str, factory, description: str, attempts: int = 12) -> str:
        domain = mailbox_domain(user)
        last_error: Exception | None = None
        for _ in range(attempts):
            address = f"{validate_local_part(factory())}@{domain}"
            try:
                await client(request).create_alias(address, user, description)
                return address
            except MailcowError as exc:
                last_error = exc
        raise MailcowError(f"Could not create a unique alias after {attempts} attempts: {last_error}")

    @app.get("/healthz", response_class=PlainTextResponse)
    async def healthz() -> str:
        return "ok\n"

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        if request.session.get("user_email"):
            return RedirectResponse("/aliases", status_code=303)
        return TEMPLATES.TemplateResponse(request, "index.html", {"version": __version__})

    @app.get("/login")
    async def login(request: Request):
        return RedirectResponse(authorization_url(request, settings), status_code=302)

    @app.get("/oauth/callback")
    async def oauth_callback(request: Request, code: str | None = None, state: str | None = None):
        validate_oauth_state(request, state)
        if not code:
            raise HTTPException(status_code=400, detail="Missing OAuth code")
        try:
            profile = await exchange_code(settings, code)
            email = str(profile.get("email") or profile.get("username") or "").strip().lower()
            if not email:
                raise OAuthError("mailcow profile does not contain a mailbox address")
            mailbox = await client(request).get_mailbox(email)
            mailbox_username = str(mailbox.get("username") or email).lower()
            if mailbox_username != email:
                raise OAuthError("mailcow profile and API mailbox do not match")
        except (OAuthError, MailcowError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        request.session.clear()
        request.session["user_email"] = email
        ensure_csrf_token(request)
        return RedirectResponse("/aliases", status_code=303)

    @app.post("/logout")
    async def logout(request: Request, csrf_token: str = Form(...)):
        validate_csrf(request, csrf_token)
        request.session.clear()
        return RedirectResponse("/", status_code=303)

    @app.get("/aliases", response_class=HTMLResponse)
    async def aliases_dashboard(request: Request):
        user = require_user(request)
        try:
            all_aliases = await client(request).list_aliases()
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        owned = [alias for alias in all_aliases if is_owned_alias(alias, user)]
        reserved = sorted((alias for alias in owned if alias.is_reserved), key=lambda item: item.address)
        assigned = sorted((alias for alias in owned if not alias.is_reserved), key=lambda item: (item.description.lower(), item.address))
        return TEMPLATES.TemplateResponse(request, "dashboard.html", {"user": user, "domain": mailbox_domain(user), "assigned": assigned, "reserved": reserved, "csrf_token": ensure_csrf_token(request), "wordlist": settings.wordlist, "version": __version__})

    @app.post("/aliases")
    async def create_alias(request: Request, mode: str = Form(...), description: str = Form(...), local_part: str = Form(""), csrf_token: str = Form(...)):
        validate_csrf(request, csrf_token)
        user = require_user(request)
        description = description.strip()
        if not description or len(description) > 160:
            raise HTTPException(status_code=400, detail="Description must be 1-160 characters")
        try:
            if mode == "readable":
                await create_unique_alias(request, user, lambda: readable_local_part(settings.wordlist), description)
            elif mode == "named":
                await create_unique_alias(request, user, lambda: named_local_part(description), description)
            elif mode == "custom":
                address = f"{validate_local_part(local_part)}@{mailbox_domain(user)}"
                await client(request).create_alias(address, user, description)
            else:
                raise HTTPException(status_code=400, detail="Unknown alias mode")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse("/aliases", status_code=303)

    @app.post("/aliases/pool")
    async def create_pool(request: Request, count: int = Form(...), csrf_token: str = Form(...)):
        validate_csrf(request, csrf_token)
        user = require_user(request)
        if count not in {1, 5, 10, 20}:
            raise HTTPException(status_code=400, detail="Pool size must be 1, 5, 10 or 20")
        try:
            for _ in range(count):
                await create_unique_alias(request, user, lambda: readable_local_part(settings.wordlist), RESERVED_COMMENT)
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse("/aliases#pool", status_code=303)

    @app.get("/aliases/pool.txt", response_class=PlainTextResponse)
    async def export_pool(request: Request):
        user = require_user(request)
        aliases = await client(request).list_aliases()
        reserved = sorted(alias.address for alias in aliases if is_owned_alias(alias, user) and alias.is_reserved and alias.active)
        return PlainTextResponse("\n".join(reserved) + ("\n" if reserved else ""))

    @app.post("/aliases/{alias_id}/description")
    async def update_description(request: Request, alias_id: int, description: str = Form(...), csrf_token: str = Form(...)):
        validate_csrf(request, csrf_token)
        await owned_alias(request, alias_id)
        description = description.strip()
        if not description or len(description) > 160:
            raise HTTPException(status_code=400, detail="Description must be 1-160 characters")
        try:
            # Only the mailcow comment changes. Alias addresses are immutable in Cowcloak.
            await client(request).update_description(alias_id, description)
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse("/aliases", status_code=303)

    @app.post("/aliases/{alias_id}/toggle")
    async def toggle_alias(request: Request, alias_id: int, csrf_token: str = Form(...)):
        validate_csrf(request, csrf_token)
        _, alias = await owned_alias(request, alias_id)
        try:
            await client(request).set_active(alias_id, not alias.active)
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse("/aliases", status_code=303)

    return app


app = create_app()
