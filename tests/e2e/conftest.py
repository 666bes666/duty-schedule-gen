from __future__ import annotations

import subprocess
import time
from collections.abc import Generator

import httpx
import pytest


@pytest.fixture(scope="session")
def streamlit_server() -> Generator[str, None, None]:
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "streamlit",
            "run",
            "app.py",
            "--server.headless",
            "true",
            "--server.port",
            "8502",
            "--server.enableCORS",
            "false",
            "--browser.gatherUsageStats",
            "false",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base_url = "http://localhost:8502"

    for _ in range(30):
        try:
            resp = httpx.get(f"{base_url}/_stcore/health", timeout=2)
            if resp.status_code == 200:
                break
        except httpx.ConnectError:
            pass
        time.sleep(1)
    else:
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=5)
        pytest.fail(
            f"Streamlit did not start within 30 seconds\n"
            f"stdout: {stdout.decode(errors='replace')}\n"
            f"stderr: {stderr.decode(errors='replace')}"
        )

    yield base_url

    proc.terminate()
    proc.wait(timeout=5)
