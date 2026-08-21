from __future__ import annotations

import os
import re
import smtplib
import ssl
import subprocess
import time
import warnings
from pathlib import Path

import httpx
import pytest

DOMAIN = "moolias-sender-pcre.test"
MAILBOX = f"owner@{DOMAIN}"
ALIAS = f"service@{DOMAIN}"
PASSWORD = "Moolias-Sender-PCRE-CI-4f9d!A7"
PCRE_CONTAINER_PATH = "/opt/postfix/conf/moolias/blocked_sender_login.pcre"
SENDER_ACL_SQL_PATH = "/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf"
BLOCKED_OWNER = "__moolias_blocked_primary_sender__"


def _result_types(body: object) -> list[str]:
    entries = body if isinstance(body, list) else [body]
    return [
        str(entry.get("type", "")).strip().casefold()
        for entry in entries
        if isinstance(entry, dict)
    ]


async def _post_success(
    admin: httpx.AsyncClient,
    path: str,
    payload: dict[str, object],
) -> object:
    response = await admin.post(path, json=payload)
    response.raise_for_status()
    body = response.json()
    if "success" not in _result_types(body):
        raise AssertionError(f"Mailcow {path} did not report success: {body!r}")
    return body


def _mailcow_dir() -> Path:
    raw = os.environ.get("MAILCOW_DIR")
    if not raw:
        pytest.skip("MAILCOW_DIR is not configured")
    return Path(raw)


def _compose(*args: str) -> str:
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=_mailcow_dir(),
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _postfix(*args: str) -> str:
    return _compose(
        "exec",
        "-T",
        "postfix-mailcow",
        "postfix",
        "-c",
        "/opt/postfix/conf",
        *args,
    )


def _postconf(name: str) -> str:
    return _compose(
        "exec",
        "-T",
        "postfix-mailcow",
        "postconf",
        "-c",
        "/opt/postfix/conf",
        name,
    )


def _postfix_container_id() -> str:
    return _compose("ps", "-q", "postfix-mailcow")


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.chmod(0o644)
    temporary.replace(path)


def _smtp_mail_from(sender: str) -> tuple[int, str]:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with smtplib.SMTP("127.0.0.1", 587, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(MAILBOX, PASSWORD)
        code, response = smtp.mail(sender)
        return code, response.decode("utf-8", errors="replace")


def _smtp_mail_from_when_ready(sender: str) -> tuple[int, str]:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            return _smtp_mail_from(sender)
        except (OSError, smtplib.SMTPException) as exc:
            last_error = exc
            time.sleep(1)
    raise AssertionError(f"Mailcow submission did not become ready: {last_error!r}")


def _smtp_codes(sender: str, attempts: int = 6) -> list[int]:
    return [_smtp_mail_from_when_ready(sender)[0] for _ in range(attempts)]


def _accepted(codes: list[int]) -> bool:
    return bool(codes) and all(code == 250 for code in codes)


def _rejected(codes: list[int]) -> bool:
    return bool(codes) and all(code >= 500 for code in codes)


async def test_primary_sender_pcre_changes_without_container_restart() -> None:
    base_url = os.environ.get("MAILCOW_URL")
    api_key = os.environ.get("MAILCOW_API_KEY")
    if not base_url or not api_key:
        pytest.skip("real Mailcow integration environment is not configured")

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        timeout=30.0,
        trust_env=False,
    ) as admin:
        await _post_success(
            admin,
            "/api/v1/add/domain",
            {
                "active": 1,
                "aliases": 10,
                "backupmx": 0,
                "defquota": 128,
                "description": "Moolias sender PCRE spike",
                "domain": DOMAIN,
                "mailboxes": 2,
                "maxquota": 512,
                "quota": 1024,
                "relay_all_recipients": 0,
                "rl_frame": "s",
                "rl_value": 10,
                "restart_sogo": 0,
            },
        )
        await _post_success(
            admin,
            "/api/v1/add/mailbox",
            {
                "active": 1,
                "domain": DOMAIN,
                "local_part": "owner",
                "name": "Moolias Sender PCRE CI",
                "password": PASSWORD,
                "password2": PASSWORD,
                "quota": 128,
                "force_pw_update": 0,
                "tls_enforce_in": 0,
                "tls_enforce_out": 0,
            },
        )
        await _post_success(
            admin,
            "/api/v1/add/alias",
            {
                "active": 1,
                "address": ALIAS,
                "goto": MAILBOX,
                "private_comment": "moolias-sender-pcre-spike",
                "public_comment": "",
                "sender_allowed": 1,
                "sogo_visible": 1,
            },
        )

    baseline_primary = _smtp_mail_from_when_ready(MAILBOX)
    baseline_alias = _smtp_mail_from_when_ready(ALIAS)
    assert baseline_primary[0] == 250, baseline_primary
    assert baseline_alias[0] == 250, baseline_alias

    postfix_conf_dir = _mailcow_dir() / "data" / "conf" / "postfix"
    pcre_path = postfix_conf_dir / "moolias" / "blocked_sender_login.pcre"
    extra_cf = postfix_conf_dir / "extra.cf"
    original_extra_cf = extra_cf.read_text(encoding="utf-8") if extra_cf.exists() else ""

    override = (
        "smtpd_sender_login_maps =\n"
        f"  pcre:{PCRE_CONTAINER_PATH},\n"
        f"  proxy:mysql:{SENDER_ACL_SQL_PATH}\n"
    )
    if override not in original_extra_cf:
        updated_extra_cf = f"{original_extra_cf.rstrip()}\n\n{override}".lstrip("\n")
        _write_atomic(extra_cf, updated_extra_cf)
    _write_atomic(pcre_path, "# Moolias sender restriction spike\n")

    # This restart represents the one-time installation of the extra.cf map.
    # Dynamic sender toggles below only rewrite the PCRE file.
    _compose("restart", "postfix-mailcow")
    _smtp_mail_from_when_ready(MAILBOX)

    active_maps = _postconf("smtpd_sender_login_maps")
    assert f"pcre:{PCRE_CONTAINER_PATH}" in active_maps, active_maps
    assert f"proxy:mysql:{SENDER_ACL_SQL_PATH}" in active_maps, active_maps
    assert active_maps.index(f"pcre:{PCRE_CONTAINER_PATH}") < active_maps.index(
        f"proxy:mysql:{SENDER_ACL_SQL_PATH}"
    )

    container_id = _postfix_container_id()
    assert container_id

    configured_primary = _smtp_codes(MAILBOX)
    configured_alias = _smtp_codes(ALIAS)
    assert _accepted(configured_primary), configured_primary
    assert _accepted(configured_alias), configured_alias

    rule = rf"/^{re.escape(MAILBOX)}$/ {BLOCKED_OWNER}\n"
    _write_atomic(pcre_path, rule)

    blocked_without_reload_codes = _smtp_codes(MAILBOX)
    blocked_without_reload = _rejected(blocked_without_reload_codes)

    blocked_after_reload_codes: list[int] | None = None
    if not blocked_without_reload:
        _postfix("reload")
        blocked_after_reload_codes = _smtp_codes(MAILBOX)
        assert _rejected(blocked_after_reload_codes), blocked_after_reload_codes

    alias_while_blocked = _smtp_codes(ALIAS)
    assert _accepted(alias_while_blocked), alias_while_blocked
    assert _postfix_container_id() == container_id

    _write_atomic(pcre_path, "# Moolias sender restriction spike\n")

    unblocked_without_reload_codes = _smtp_codes(MAILBOX)
    unblocked_without_reload = _accepted(unblocked_without_reload_codes)

    unblocked_after_reload_codes: list[int] | None = None
    if not unblocked_without_reload:
        _postfix("reload")
        unblocked_after_reload_codes = _smtp_codes(MAILBOX)
        assert _accepted(unblocked_after_reload_codes), unblocked_after_reload_codes

    final_alias = _smtp_codes(ALIAS)
    assert _accepted(final_alias), final_alias
    assert _postfix_container_id() == container_id

    warnings.warn(
        "Sender PCRE spike: "
        f"blocked_without_reload={blocked_without_reload!r}, "
        f"blocked_codes={blocked_without_reload_codes!r}, "
        f"blocked_after_reload_codes={blocked_after_reload_codes!r}, "
        f"unblocked_without_reload={unblocked_without_reload!r}, "
        f"unblocked_codes={unblocked_without_reload_codes!r}, "
        f"unblocked_after_reload_codes={unblocked_after_reload_codes!r}, "
        f"alias_while_blocked={alias_while_blocked!r}",
        stacklevel=1,
    )
