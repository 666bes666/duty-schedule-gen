from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.ui
class TestExportDownload:
    def test_page_accessible(self, page: Page, streamlit_url: str):
        response = page.goto(streamlit_url, wait_until="networkidle")
        assert response is not None
        assert response.status == 200
