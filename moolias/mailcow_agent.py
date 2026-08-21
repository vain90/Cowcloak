from __future__ import annotations

import fcntl
import hmac
import json
import math
import os
import re
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from moolias import __version__
from moolias.sender_protocol import (
    NONCE_HEADER,
    PROTOCOL_VERSION,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    InvalidMailbox,
    normalize_mailbox,
    request_signature,
)

BLOCKED_OWNER = "__moolias_blocked_primary_sender__"
DEFAULT_STATE_DIR = "/state"
DEFAULT_COOLDOWN_SECONDS = 10
MAX_CLOCK_SKEW_SECONDS = 30
NONCE_TTL_SECONDS = 60
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


class AgentConfigurationError(RuntimeError):
    pass


class AgentStateError(RuntimeError):
    pass


class AgentCooldownError(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Cooldown active for {retry_after} seconds")
        self.retry_after = max(1, retry_after)


class MailboxRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mailbox: str


class ProtectionRequest(MailboxRequest):
    blocked: bool


class AgentAuthenticator:
    def __init__(
        self,
        secret: str,
        *,
        clock: Callable[[], float] = time.time,
        max_clock_skew: int = MAX_CLOCK_SKEW_SECONDS,
        nonce_ttl: int = NONCE_TTL_SECONDS,
    ) -> None:
        if len(secret) < 32:
            raise AgentConfigurationError("MOOLIAS_AGENT_SECRET must be at least 32 characters")
        self.secret = secret
        self.clock = clock
        self.max_clock_skew = max_clock_skew
        self.nonce_ttl = nonce_ttl
        self._nonces: dict[str, float] = {}
        self._lock = threading.Lock()

    def verify(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        timestamp_value: str | None,
        nonce: str | None,
        signature: str | None,
    ) -> None:
        if not timestamp_value or not nonce or not signature:
            raise HTTPException(status_code=401, detail="Missing agent authentication")
        try:
            timestamp = int(timestamp_value)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Invalid agent timestamp") from exc

        now = self.clock()
        if abs(now - timestamp) > self.max_clock_skew:
            raise HTTPException(status_code=401, detail="Expired agent request")
        if not _NONCE_RE.fullmatch(nonce):
            raise HTTPException(status_code=401, detail="Invalid agent nonce")

        expected = request_signature(
            self.secret,
            method,
            path,
            timestamp,
            nonce,
            body,
        )
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid agent signature")

        with self._lock:
            cutoff = now - self.nonce_ttl
            self._nonces = {
                known_nonce: seen_at
                for known_nonce, seen_at in self._nonces.items()
                if seen_at >= cutoff
            }
            if nonce in self._nonces:
                raise HTTPException(status_code=401, detail="Replayed agent request")
            self._nonces[nonce] = now


class AgentStateStore:
    def __init__(
        self,
        state_dir: str | Path,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if cooldown_seconds < 1 or cooldown_seconds > 300:
            raise AgentConfigurationError("Agent cooldown must be between 1 and 300 seconds")
        self.state_dir = Path(state_dir)
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self.state_path = self.state_dir / "state.json"
        self.pcre_path = self.state_dir / "blocked_sender_login.pcre"
        self.lock_path = self.state_dir / ".lock"

    def ensure_files(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            state = self._load_state()
            self._write_state_and_pcre(state)

    def status(self, mailbox: str) -> dict[str, Any]:
        mailbox = normalize_mailbox(mailbox)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            state = self._load_state()
            self._reconcile_pcre(state)
            blocked = mailbox in set(state["blocked"])
            return {
                "mailbox": mailbox,
                "blocked": blocked,
                "retry_after": self._retry_after(state, mailbox),
            }

    def set_blocked(self, mailbox: str, blocked: bool) -> dict[str, Any]:
        mailbox = normalize_mailbox(mailbox)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            state = self._load_state()
            blocked_set = set(state["blocked"])
            current = mailbox in blocked_set
            if current == blocked:
                self._reconcile_pcre(state)
                return {
                    "mailbox": mailbox,
                    "blocked": current,
                    "changed": False,
                    "retry_after": self._retry_after(state, mailbox),
                }

            retry_after = self._retry_after(state, mailbox)
            if retry_after:
                raise AgentCooldownError(retry_after)

            if blocked:
                blocked_set.add(mailbox)
            else:
                blocked_set.discard(mailbox)

            now = self.clock()
            state["blocked"] = sorted(blocked_set)
            last_changed = {
                str(key): float(value)
                for key, value in state["last_changed"].items()
                if now - float(value) <= 86400 or key in blocked_set
            }
            last_changed[mailbox] = now
            state["last_changed"] = last_changed
            self._write_state_and_pcre(state)
            return {
                "mailbox": mailbox,
                "blocked": blocked,
                "changed": True,
                "retry_after": self.cooldown_seconds,
            }

    def _retry_after(self, state: dict[str, Any], mailbox: str) -> int:
        changed_at = state["last_changed"].get(mailbox)
        if changed_at is None:
            return 0
        remaining = self.cooldown_seconds - (self.clock() - float(changed_at))
        return max(0, math.ceil(remaining))

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"version": 1, "blocked": [], "last_changed": {}}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AgentStateError("Could not read sender protection state") from exc
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise AgentStateError("Unsupported sender protection state")
        blocked_raw = payload.get("blocked")
        changed_raw = payload.get("last_changed")
        if not isinstance(blocked_raw, list) or not isinstance(changed_raw, dict):
            raise AgentStateError("Invalid sender protection state")
        try:
            blocked = sorted({normalize_mailbox(str(item)) for item in blocked_raw})
            last_changed = {
                normalize_mailbox(str(key)): float(value)
                for key, value in changed_raw.items()
            }
        except (InvalidMailbox, TypeError, ValueError) as exc:
            raise AgentStateError("Invalid sender protection state") from exc
        return {"version": 1, "blocked": blocked, "last_changed": last_changed}

    def _render_pcre(self, state: dict[str, Any]) -> str:
        lines = [
            "# Managed by Moolias Mailcow Agent. Do not edit manually.",
            "# Changes are loaded by new Postfix smtpd processes without a service restart.",
        ]
        for mailbox in state["blocked"]:
            escaped = re.escape(mailbox).replace("/", r"\/")
            lines.append(f"/^{escaped}$/    {BLOCKED_OWNER}")
        return "\n".join(lines) + "\n"

    def _reconcile_pcre(self, state: dict[str, Any]) -> None:
        expected = self._render_pcre(state)
        try:
            current = self.pcre_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = ""
        if current != expected:
            self._atomic_write(self.pcre_path, expected, mode=0o644)

    def _write_state_and_pcre(self, state: dict[str, Any]) -> None:
        state_text = json.dumps(
            state,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
        pcre_text = self._render_pcre(state)
        self._atomic_write(self.state_path, state_text, mode=0o600)
        try:
            self._atomic_write(self.pcre_path, pcre_text, mode=0o644)
        except Exception:
            # A later status call or process restart reconciles the PCRE from state.
            raise

    def _atomic_write(self, path: Path, content: str, *, mode: int) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(mode)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


def create_agent_app(
    *,
    secret: str | None = None,
    state_dir: str | Path | None = None,
    cooldown_seconds: int | None = None,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    resolved_secret = secret if secret is not None else os.environ.get("MOOLIAS_AGENT_SECRET", "")
    resolved_state_dir = state_dir or os.environ.get("MOOLIAS_AGENT_STATE_DIR", DEFAULT_STATE_DIR)
    if cooldown_seconds is None:
        raw_cooldown = os.environ.get(
            "MOOLIAS_AGENT_COOLDOWN_SECONDS",
            str(DEFAULT_COOLDOWN_SECONDS),
        )
        try:
            cooldown_seconds = int(raw_cooldown)
        except ValueError as exc:
            raise AgentConfigurationError(
                "MOOLIAS_AGENT_COOLDOWN_SECONDS must be an integer"
            ) from exc

    authenticator = AgentAuthenticator(resolved_secret, clock=clock)
    store = AgentStateStore(resolved_state_dir, cooldown_seconds, clock=clock)
    store.ensure_files()

    app = FastAPI(
        title="Moolias Mailcow Agent",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.authenticator = authenticator
    app.state.store = store

    @app.get("/healthz")
    async def healthz():
        return {
            "status": "ok",
            "protocol": PROTOCOL_VERSION,
            "version": __version__,
        }

    async def authenticated_payload(
        request: Request,
        model: type[BaseModel],
    ) -> BaseModel:
        body = await request.body()
        authenticator.verify(
            method=request.method,
            path=request.url.path,
            body=body,
            timestamp_value=request.headers.get(TIMESTAMP_HEADER),
            nonce=request.headers.get(NONCE_HEADER),
            signature=request.headers.get(SIGNATURE_HEADER),
        )
        try:
            return model.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail="Invalid agent request") from exc

    @app.post("/v1/status")
    async def status_endpoint(request: Request):
        payload = await authenticated_payload(request, MailboxRequest)
        try:
            return store.status(payload.mailbox)
        except (InvalidMailbox, AgentStateError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/protection")
    async def protection_endpoint(request: Request):
        payload = await authenticated_payload(request, ProtectionRequest)
        try:
            return store.set_blocked(payload.mailbox, payload.blocked)
        except AgentCooldownError as exc:
            raise HTTPException(
                status_code=429,
                detail="Sender protection cooldown is active",
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except InvalidMailbox as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AgentStateError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app
