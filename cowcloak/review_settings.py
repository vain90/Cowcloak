from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request

from cowcloak.aliases import is_owned_alias, is_primary_mailbox_alias
from cowcloak.security import require_user, validate_csrf

router = APIRouter()


class AliasReviewSettingsStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sender_alias_settings (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                ignore_unexpected INTEGER NOT NULL DEFAULT 0
                    CHECK (ignore_unexpected IN (0, 1)),
                PRIMARY KEY (mailbox, alias)
            )
            """
        )
        return connection

    async def ignored_aliases(self, mailbox: str) -> set[str]:
        return await asyncio.to_thread(self._ignored_aliases, mailbox)

    def _ignored_aliases(self, mailbox: str) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT alias
                FROM sender_alias_settings
                WHERE mailbox = ? AND ignore_unexpected = 1
                """,
                (mailbox.lower(),),
            ).fetchall()
        return {str(row["alias"]).lower() for row in rows}

    async def set_ignore_unexpected(
        self,
        mailbox: str,
        alias: str,
        ignored: bool,
    ) -> None:
        await asyncio.to_thread(
            self._set_ignore_unexpected,
            mailbox,
            alias,
            ignored,
        )

    def _set_ignore_unexpected(
        self,
        mailbox: str,
        alias: str,
        ignored: bool,
    ) -> None:
        mailbox = mailbox.lower()
        alias = alias.lower()
        with self._connect() as connection:
            if ignored:
                connection.execute(
                    """
                    INSERT INTO sender_alias_settings (
                        mailbox,
                        alias,
                        ignore_unexpected
                    ) VALUES (?, ?, 1)
                    ON CONFLICT(mailbox, alias) DO UPDATE SET
                        ignore_unexpected = 1
                    """,
                    (mailbox, alias),
                )
            else:
                connection.execute(
                    """
                    DELETE FROM sender_alias_settings
                    WHERE mailbox = ? AND alias = ?
                    """,
                    (mailbox, alias),
                )


def _store(request: Request) -> AliasReviewSettingsStore | None:
    stats_store = getattr(request.app.state, "stats_store", None)
    if stats_store is None:
        return None
    return AliasReviewSettingsStore(stats_store.path)


@router.get("/aliases/review-settings")
async def get_alias_review_settings(request: Request):
    user = require_user(request)
    store = _store(request)
    if store is None:
        return {"ignored_unexpected": []}
    ignored = await store.ignored_aliases(user)
    return {"ignored_unexpected": sorted(ignored)}


@router.post("/aliases/{alias_id}/unexpected-monitoring")
async def update_unexpected_monitoring(
    request: Request,
    alias_id: int,
    ignored: bool = Form(False),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    store = _store(request)
    if store is None:
        raise HTTPException(status_code=409, detail="Usage statistics are disabled")

    alias = await request.app.state.mailcow.get_alias(alias_id)
    if (
        not is_owned_alias(alias, user)
        or alias.is_reserved
        or is_primary_mailbox_alias(alias, user)
    ):
        raise HTTPException(status_code=403, detail="Alias cannot be managed here")

    await store.set_ignore_unexpected(user, alias.address, ignored)
    return {
        "alias": alias.address,
        "ignored": ignored,
    }
