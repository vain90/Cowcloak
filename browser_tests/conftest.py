from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BROWSER_TEST_DIR = Path(__file__).resolve().parent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            raise RuntimeError(f"E2E server exited early:\n{output}")
        try:
            with urllib.request.urlopen(f"{url}/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    raise RuntimeError("E2E server did not become healthy within 20 seconds")


@pytest.fixture(scope="session")
def base_url(tmp_path_factory) -> str:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    database = tmp_path_factory.mktemp("cowcloak-e2e") / "stats.sqlite3"
    env = os.environ.copy()
    env["COWCLOAK_E2E_BASE_URL"] = url
    env["COWCLOAK_E2E_DB"] = str(database)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(ROOT), env.get("PYTHONPATH", "")) if part
    )

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "e2e_app:app",
            "--app-dir",
            str(BROWSER_TEST_DIR),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_server(url, process)
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture(autouse=True)
def reset_e2e_state(base_url: str) -> None:
    request = urllib.request.Request(f"{base_url}/__e2e__/reset", method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 204
