from __future__ import annotations

import os
import re
import smtplib
import ssl
import subprocess
import time

import httpx
import pytest

from moolias.sender_protection import SenderAgentClient

DOMAIN = "moolias-sender-agent.test"
MAILBOX = f"owner@{DOMAIN}"
ALIAS = f"service@{DOMAIN}"
PASSWORD = "Moolias-Sender-Agent-CI-4f9d!A7"
LEGACY_MAILBOX = "legacy.blocked@example.org"
BLOCKED_OWNER = "__moolias_blocked_primary_sender__"
PCRE_MAP = "pcre:/opt/postfix/conf/moolias/blocked_sender_login.pcre"


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
) -> None:
    response = await admin.post(path, json=payload)
    response.raise_for_status()
    body = response.json()
    if "success" not in _result_types(body):
        raise AssertionError(f"Mailcow {path} did not report success: {body!r}")


def _smtp_envelope(sender: str) -> tuple[int, str, int, str]:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with smtplib.SMTP("127.0.0.1", 587, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(MAILBOX, PASSWORD)
        mail_code, mail_response = smtp.mail(sender)
        rcpt_code, rcpt_response = smtp.rcpt(MAILBOX)
        return (
            mail_code,
            mail_response.decode("utf-8", errors="replace"),
            rcpt_code,
            rcpt_response.decode("utf-8", errors="replace"),
        )


def _smtp_envelope_when_ready(sender: str) -> tuple[int, str, int, str]:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            return _smtp_envelope(sender)
        except (OSError, smtplib.SMTPException) as exc:
            last_error = exc
            time.sleep(1)
    raise AssertionError(f"Mailcow submission did not become ready: {last_error!r}")


def _postfix_container_id(mailcow_dir: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "ps", "-q", "postfix-mailcow"],
        cwd=mailcow_dir,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _postfix_map_query(mailcow_dir: str, mailbox: str) -> tuple[str, str]:
    lookup = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postfix-mailcow",
            "postmap",
            "-q",
            mailbox,
            PCRE_MAP,
        ],
        cwd=mailcow_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    rendered = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postfix-mailcow",
            "cat",
            "/opt/postfix/conf/moolias/blocked_sender_login.pcre",
        ],
        cwd=mailcow_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    return lookup, rendered


def _prepare_legacy_sender_block(mailcow_dir: str) -> None:
    postfix_dir = os.path.join(mailcow_dir, "data", "conf", "postfix")
    legacy_pcre = os.path.join(postfix_dir, "blocked_sender_login.pcre")
    extra_cf = os.path.join(postfix_dir, "extra.cf")

    subprocess.run(
        ["sudo", "install", "-d", "-m", "0755", postfix_dir],
        check=True,
    )
    subprocess.run(
        ["sudo", "tee", legacy_pcre],
        input=r"/^legacy\.blocked@example\.org$/    __blocked_hidden_sender__" + "\n",
        check=True,
        text=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["sudo", "tee", "-a", extra_cf],
        input=(
            "\nsmtpd_sender_login_maps = "
            "pcre:/opt/postfix/conf/blocked_sender_login.pcre, "
            "proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf\n"
        ),
        check=True,
        text=True,
        stdout=subprocess.DEVNULL,
    )


def _install_agent(mailcow_dir: str) -> str:
    image = os.environ.get("MOOLIAS_AGENT_IMAGE", "moolias:sender-agent-ci")
    env = os.environ.copy()
    env["MAILCOW_DIR"] = mailcow_dir
    env["MOOLIAS_AGENT_IMAGE"] = image
    env["MOOLIAS_AGENT_COOLDOWN_SECONDS"] = "1"

    result = subprocess.run(
        [
            "sudo",
            "--preserve-env=MAILCOW_DIR,MOOLIAS_AGENT_IMAGE,MOOLIAS_AGENT_COOLDOWN_SECONDS",
            "bash",
            "scripts/install-mailcow-agent.sh",
        ],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Moolias Mailcow Agent installer failed:\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    match = re.search(r"^MOOLIAS_SENDER_AGENT_SECRET=(.+)$", result.stdout, re.MULTILINE)
    if match is None:
        raise AssertionError(f"Installer did not print the agent secret:\n{result.stdout}")
    return match.group(1).strip()


async def test_bootstrap_agent_blocks_only_primary_sender_without_runtime_restart() -> None:
    base_url = os.environ.get("MAILCOW_URL")
    api_key = os.environ.get("MAILCOW_API_KEY")
    mailcow_dir = os.environ.get("MAILCOW_DIR")
    if not base_url or not api_key or not mailcow_dir:
        pytest.skip("real Mailcow integration environment is not configured")

    _prepare_legacy_sender_block(mailcow_dir)
    secret = _install_agent(mailcow_dir)

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
                "description": "Moolias sender agent integration",
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
                "name": "Moolias Sender Agent CI",
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
                "private_comment": "moolias-sender-agent-integration",
                "public_comment": "",
                "sender_allowed": 1,
                "sogo_visible": 1,
            },
        )

    baseline_primary = _smtp_envelope_when_ready(MAILBOX)
    baseline_alias = _smtp_envelope_when_ready(ALIAS)
    assert baseline_primary[0] == 250, baseline_primary
    assert baseline_primary[2] == 250, baseline_primary
    assert baseline_alias[0] == 250, baseline_alias
    assert baseline_alias[2] == 250, baseline_alias

    public_agent_url = f"{base_url.rstrip('/')}/moolias-agent"

    # The nginx route is reachable, but unauthenticated callers cannot change state.
    async with httpx.AsyncClient(
        base_url=f"{public_agent_url}/",
        timeout=10.0,
        trust_env=False,
    ) as unauthenticated:
        health = await unauthenticated.get("healthz")
        assert health.status_code == 200
        unsigned = await unauthenticated.post(
            "v1/protection",
            json={"mailbox": MAILBOX, "blocked": True},
        )
        assert unsigned.status_code == 401

    postfix_id = _postfix_container_id(mailcow_dir)
    assert postfix_id

    active_maps = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postfix-mailcow",
            "postconf",
            "-c",
            "/opt/postfix/conf",
            "smtpd_sender_login_maps",
        ],
        cwd=mailcow_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert PCRE_MAP in active_maps
    assert "pcre:/opt/postfix/conf/blocked_sender_login.pcre" not in active_maps

    for service in ("smtps", "submission", "588"):
        max_use = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postfix-mailcow",
                "postconf",
                "-c",
                "/opt/postfix/conf",
                "-P",
                f"{service}/inet/max_use",
            ],
            cwd=mailcow_dir,
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        assert re.search(r"=\s*1\s*$", max_use), max_use

    async with SenderAgentClient(
        public_agent_url,
        secret,
        verify_tls=False,
    ) as agent:
        await agent.probe()
        initial = await agent.status(MAILBOX)
        assert initial.blocked is False

        migrated = await agent.status(LEGACY_MAILBOX)
        assert migrated.blocked is True

        blocked, changed = await agent.set_blocked(MAILBOX, True)
        assert changed is True
        assert blocked.blocked is True

        lookup, rendered = _postfix_map_query(mailcow_dir, MAILBOX)
        assert lookup == BLOCKED_OWNER, (
            f"Postfix PCRE lookup returned {lookup!r}; rendered map:\n{rendered}"
        )

        blocked_primary = _smtp_envelope_when_ready(MAILBOX)
        allowed_alias = _smtp_envelope_when_ready(ALIAS)
        # Mailcow keeps smtpd_delay_reject enabled, so sender restrictions are
        # evaluated at RCPT TO rather than at MAIL FROM.
        assert blocked_primary[0] == 250, blocked_primary
        assert blocked_primary[2] >= 500, blocked_primary
        assert allowed_alias[0] == 250, allowed_alias
        assert allowed_alias[2] == 250, allowed_alias
        assert _postfix_container_id(mailcow_dir) == postfix_id

        time.sleep(1.1)
        unblocked, changed = await agent.set_blocked(MAILBOX, False)
        assert changed is True
        assert unblocked.blocked is False

        lookup, rendered = _postfix_map_query(mailcow_dir, MAILBOX)
        assert lookup == "", (
            f"Postfix PCRE lookup still returned {lookup!r}; rendered map:\n{rendered}"
        )

    allowed_primary = _smtp_envelope_when_ready(MAILBOX)
    assert allowed_primary[0] == 250, allowed_primary
    assert allowed_primary[2] == 250, allowed_primary
    assert _postfix_container_id(mailcow_dir) == postfix_id
