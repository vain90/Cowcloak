from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def test_installer_completes_when_supplied_through_stdin() -> None:
    mailcow_dir = os.environ.get("MAILCOW_DIR")
    if not mailcow_dir:
        pytest.skip("real Mailcow integration environment is not configured")

    installer = Path(__file__).resolve().parents[1] / "scripts" / "install-mailcow-agent.sh"
    env = os.environ.copy()
    env["MAILCOW_DIR"] = mailcow_dir
    env["MOOLIAS_AGENT_IMAGE"] = os.environ.get(
        "MOOLIAS_AGENT_IMAGE",
        "moolias:sender-agent-ci",
    )
    env["MOOLIAS_AGENT_COOLDOWN_SECONDS"] = "1"
    env["MOOLIAS_IMPORT_EXISTING_SENDER_RULES"] = "no"

    result = subprocess.run(
        [
            "sudo",
            "--preserve-env="
            "MAILCOW_DIR,MOOLIAS_AGENT_IMAGE,MOOLIAS_AGENT_COOLDOWN_SECONDS,"
            "MOOLIAS_IMPORT_EXISTING_SENDER_RULES",
            "bash",
        ],
        input=installer.read_text(encoding="utf-8"),
        cwd=mailcow_dir,
        check=False,
        text=True,
        capture_output=True,
        env=env,
        timeout=120,
    )

    assert result.returncode == 0, (
        "Piped installer failed:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    assert "Moolias Mailcow Agent installed successfully" in result.stdout
    assert "NEXT STEP: Configure Moolias" in result.stdout
    assert "MOOLIAS_SENDER_AGENT_SECRET=" in result.stdout
