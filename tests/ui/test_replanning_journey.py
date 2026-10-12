import pytest
from playwright.sync_api import Page, expect

from duty_schedule.models import Schedule
from duty_schedule.project import add_revision, new_project, serialize_project
from tests.ui.fixtures import journey_config, journey_days
from tests.ui.test_product_recovery import saved, wait_saved
from tests.ui.test_project_journey import _upload


@pytest.mark.ui
def test_default_repair_and_explicit_rebuild_show_changed_cells(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    config = journey_config()
    project = add_revision(new_project(config), Schedule(config=config, days=journey_days(config)))
    _upload(page, "Открыть рабочий проект (.json)", "repair.json", serialize_project(project))
    wait_saved(page)
    page.get_by_role("button", name="Сгенерировать расписание", exact=True).click()
    expect(page.get_by_text("0 изменённых ячеек", exact=False)).to_be_visible(timeout=30000)
    wait_saved(page)
    snapshot = saved(page)
    active = snapshot["active_revisions"]["2026-04"]
    schedule = next(r["schedule"] for r in snapshot["revisions"] if r["id"] == active)
    assert schedule["metadata"]["repair"]["baseline_id"] == project.active_revisions["2026-04"]
    page.get_by_text("Полный пересчёт без сохранения назначений", exact=True).click()
    page.get_by_role("button", name="Сгенерировать расписание", exact=True).click()
    wait_saved(page)
