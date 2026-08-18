import secrets
from hmac import compare_digest

from fastapi import HTTPException, Request, status


def new_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = new_token()
        request.session["csrf_token"] = token
    return token


def validate_csrf(request: Request, supplied: str | None) -> None:
    expected = request.session.get("csrf_token")
    if not expected or not supplied or not compare_digest(expected, supplied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


def require_user(request: Request) -> str:
    email = request.session.get("user_email")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return str(email).lower()
