from __future__ import annotations

import os
import subprocess
import tempfile
import time
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest


@pytest.fixture(scope="session")
def streamlit_url() -> Generator[str, None, None]:
    external_url = os.environ.get("DUTY_TEST_STREAMLIT_URL")
    if external_url:
        yield external_url
        return
    with tempfile.TemporaryFile() as log, tempfile.TemporaryDirectory() as temp:
        runner = Path(temp) / "browser_app.py"
        runner.write_text(
            "import sys, runpy\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path.cwd()))\n"
            "from tests.ui.fixtures import journey_config\n"
            "from duty_schedule.ui import components\n"
            "from duty_schedule.calendar import CalendarError\n"
            "def saved_calendar(year, month, saved=None):\n"
            "    if (year, month) != (2026, 4):\n"
            "        raise CalendarError('Offline browser fixture supports April 2026')\n"
            "    return journey_config().production_calendar.model_copy(deep=True)\n"
            "components.fetch_production_calendar = saved_calendar\n"
            "runpy.run_path('app.py', run_name='__main__')\n"
        )
        proc = subprocess.Popen(
            [
                "uv",
                "run",
                "streamlit",
                "run",
                str(runner),
                "--server.headless",
                "true",
                "--server.port",
                "8503",
                "--server.enableCORS",
                "false",
                "--browser.gatherUsageStats",
                "false",
                "--server.fileWatcherType",
                "none",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        base_url = "http://localhost:8503"

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
            proc.wait(timeout=5)
            log.seek(0)
            output = log.read().decode(errors="replace")
            pytest.fail(f"Streamlit did not start within 30 seconds\noutput: {output}")

        yield base_url

        proc.terminate()
        proc.wait(timeout=5)
