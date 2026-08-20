from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

HISTORY_HEAD_PROBE_SIZE = 3
HISTORY_PROBE_META_KEY = "rspamd_history_head_probe_v1"
HISTORY_PROBE_COVERAGE_STATE = "healthy-probe"

_ENTRY_ID_FIELDS = ("id", "history_id", "uuid", "scan_id")
_FALLBACK_FIELDS = (
    "unix_time",
    "qid",
    "queue_id",
    "message-id",
    "message_id",
    "action",
    "user",
    "sender_smtp",
    "sender_mime",
    "rcpt_smtp",
    "score",
    "required_score",
    "size",
    "len",
    "scan_time",
    "ip",
    "symbols",
)


class UnchangedHistory(list[dict[str, Any]]):
    """Marker returned when the lightweight Rspamd head probe is unchanged."""


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _stable_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_stable_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _present(value: Any) -> bool:
    return value not in (None, "", [], {}, ())


def _entry_fingerprint(item: dict[str, Any]) -> str | None:
    for field in _ENTRY_ID_FIELDS:
        value = item.get(field)
        if _present(value):
            payload = {
                "identifier": field,
                "value": _stable_value(value),
            }
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            return hashlib.sha256(encoded).hexdigest()

    fingerprint = {
        field: _stable_value(item[field])
        for field in _FALLBACK_FIELDS
        if field in item and _present(item[field])
    }
    if "unix_time" not in fingerprint or len(fingerprint) < 2:
        return None

    encoded = json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def history_probe_fingerprints(history: list[dict[str, Any]]) -> tuple[str, ...] | None:
    if len(history) < HISTORY_HEAD_PROBE_SIZE:
        return None

    fingerprints: list[str] = []
    for item in history[:HISTORY_HEAD_PROBE_SIZE]:
        fingerprint = _entry_fingerprint(item)
        if fingerprint is None:
            return None
        fingerprints.append(fingerprint)
    return tuple(fingerprints)


class HistoryProbeStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    async def read(self) -> tuple[str, ...] | None:
        return await asyncio.to_thread(self._read)

    def _read(self) -> tuple[str, ...] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM usage_meta WHERE key = ?",
                (HISTORY_PROBE_META_KEY,),
            ).fetchone()
        if row is None:
            return None

        try:
            value = json.loads(str(row["value"]))
        except (TypeError, ValueError):
            return None
        if not isinstance(value, dict) or value.get("version") != 1:
            return None

        fingerprints = value.get("fingerprints")
        if not isinstance(fingerprints, list) or len(fingerprints) != HISTORY_HEAD_PROBE_SIZE:
            return None
        if not all(
            isinstance(fingerprint, str)
            and len(fingerprint) == 64
            and all(character in "0123456789abcdef" for character in fingerprint)
            for fingerprint in fingerprints
        ):
            return None
        return tuple(fingerprints)

    async def record_full_history(self, history: list[dict[str, Any]] | None) -> None:
        fingerprints = history_probe_fingerprints(history or [])
        await asyncio.to_thread(self._record_full_history, fingerprints)

    def _record_full_history(self, fingerprints: tuple[str, ...] | None) -> None:
        with self._connect() as connection:
            if fingerprints is None:
                connection.execute(
                    "DELETE FROM usage_meta WHERE key = ?",
                    (HISTORY_PROBE_META_KEY,),
                )
                return

            value = json.dumps(
                {"version": 1, "fingerprints": list(fingerprints)},
                separators=(",", ":"),
            )
            connection.execute(
                """
                INSERT INTO usage_meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (HISTORY_PROBE_META_KEY, value),
            )

    async def invalidate(self) -> None:
        await asyncio.to_thread(self._invalidate)

    def _invalidate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM usage_meta WHERE key = ?",
                (HISTORY_PROBE_META_KEY,),
            )

    async def record_unchanged_success(
        self,
        *,
        finished_at: int,
        duration_ms: int,
    ) -> None:
        await asyncio.to_thread(
            self._record_unchanged_success,
            finished_at,
            duration_ms,
        )

    def _record_unchanged_success(self, finished_at: int, duration_ms: int) -> None:
        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE collector_health
                SET last_success_at = ?,
                    last_error = NULL,
                    last_duration_ms = ?,
                    coverage_state = ?
                WHERE id = 1
                """,
                (finished_at, duration_ms, HISTORY_PROBE_COVERAGE_STATE),
            ).rowcount
            if updated != 1:
                raise RuntimeError("Collector health state is unavailable for history probe")
