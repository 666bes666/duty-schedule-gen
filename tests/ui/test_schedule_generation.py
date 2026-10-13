from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from duty_schedule.ui.config_io import dump_config_yaml
from tests.ui.fixtures import journey_config
from tests.ui.test_project_journey import _upload


@pytest.mark.ui
class TestScheduleGeneration:
    def test_generate_button_visible(self, page: Page, streamlit_url: str):
        page.goto(streamlit_url, wait_until="networkidle")
        expect(page.get_by_role("button", name="Добавить строку", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Сгенерировать расписание")).to_have_count(0)
        _upload(
            page,
            "Загрузить конфиг (.yaml)",
            "team.yaml",
            dump_config_yaml(journey_config()).encode(),
        )
        expect(
            page.get_by_role("button", name="Сгенерировать расписание", exact=True)
        ).to_be_visible()
