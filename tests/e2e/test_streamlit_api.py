from __future__ import annotations

import httpx
import pytest


@pytest.mark.e2e
class TestStreamlitApi:
    def test_health_endpoint(self, streamlit_server):
        resp = httpx.get(f"{streamlit_server}/_stcore/health", timeout=5)
        assert resp.status_code == 200

    def test_main_page_loads(self, streamlit_server):
        resp = httpx.get(streamlit_server, timeout=10)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_no_server_error(self, streamlit_server):
        resp = httpx.get(streamlit_server, timeout=10)
        assert resp.status_code < 500
