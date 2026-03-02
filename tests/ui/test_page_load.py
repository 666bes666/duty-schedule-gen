from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
class TestPageLoad:
    def test_page_loads_without_errors(self, page: Page, streamlit_url: str):
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        page.goto(streamlit_url, wait_until="networkidle")
        page.wait_for_timeout(2000)

        assert not errors, f"Page errors: {errors}"

    def test_page_has_title(self, page: Page, streamlit_url: str):
        page.goto(streamlit_url, wait_until="networkidle")
        assert page.title()

    def test_page_has_content(self, page: Page, streamlit_url: str):
        page.goto(streamlit_url, wait_until="networkidle")
        page.wait_for_timeout(2000)
        body = page.locator("body")
        expect(body).not_to_be_empty()
