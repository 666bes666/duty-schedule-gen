from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.ui
class TestScheduleGeneration:
    def test_generate_button_visible(self, page: Page, streamlit_url: str):
        page.goto(streamlit_url, wait_until="networkidle")
        page.wait_for_timeout(3000)

        buttons = page.get_by_role("button").all()
        button_texts = [b.inner_text() for b in buttons]
        gen_buttons = [t for t in button_texts if "генер" in t.lower() or "сгенер" in t.lower()]
        assert len(gen_buttons) > 0, f"No generate button found. Buttons: {button_texts}"
