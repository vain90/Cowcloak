from __future__ import annotations

import subprocess
from pathlib import Path

from moolias.aliases import RESERVED_COMMENT, USED_RESERVED_COMMENT, AliasRecord


def _alias(private_comment: str) -> AliasRecord:
    return AliasRecord(
        id=1,
        address="offline@example.org",
        goto="user@example.org",
        domain="example.org",
        active=True,
        private_comment=private_comment,
        public_comment="",
    )


def test_new_offline_alias_markers_use_moolias_namespace() -> None:
    assert RESERVED_COMMENT == "[moolias:reserved]"
    assert USED_RESERVED_COMMENT == "[moolias:reserved-used]"


def test_pre_rename_offline_alias_markers_remain_recognized() -> None:
    legacy = "cow" + "cloak"

    reserved = _alias(f"[{legacy}:reserved]")
    assert reserved.is_reserved
    assert not reserved.is_reserved_used

    used = _alias(f"[{legacy}:reserved-used]")
    assert used.is_reserved
    assert used.is_reserved_used


def test_legacy_brand_only_exists_in_migration_compatibility() -> None:
    legacy = "cow" + "cloak"
    tokens = (legacy, legacy.capitalize(), legacy.upper())
    allowed_document = Path("docs/migration-to-moolias.md")
    marker_file = Path("moolias/aliases.py")
    failures: list[str] = []

    tracked = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
    for raw in tracked:
        if not raw:
            continue
        path = Path(raw.decode())
        if path == allowed_document or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if path == marker_file:
            text = text.replace(f"[{legacy}:reserved]", "")
            text = text.replace(f"[{legacy}:reserved-used]", "")
        if any(token in text for token in tokens):
            failures.append(str(path))

    assert not failures, f"Legacy product name remains in: {', '.join(failures)}"
