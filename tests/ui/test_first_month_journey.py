import pytest
from playwright.sync_api import Page, expect

from duty_schedule.ui.config_io import dump_config_yaml
from tests.ui.fixtures import journey_config
from tests.ui.test_product_recovery import saved, wait_saved
from tests.ui.test_project_journey import _upload


@pytest.mark.ui
def test_preflight_explains_unknown_history_and_pin_conflict(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    config = journey_config()
    config.carry_over = []
    config.employees[0].unavailable_dates = [config.pins[0].date]
    _upload(page, "Загрузить конфиг (.yaml)", "incomplete.yaml", dump_config_yaml(config).encode())
    expect(page.get_by_text("История отдыха: требует исправления", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Сгенерировать расписание", exact=True)).to_be_disabled()
    page.get_by_text("Все причины подготовки", exact=True).click()
    expect(
        page.get_by_text("Неизвестна история до начала месяца", exact=False).first
    ).to_be_visible()


@pytest.mark.ui
def test_first_month_without_all_cell_pins_and_technical_operations(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    config = journey_config()
    config.pins = [pin for pin in config.pins if pin.employee_name == "M0" and pin.date.day == 2]
    config.solver = "cpsat"
    _upload(page, "Загрузить конфиг (.yaml)", "first.yaml", dump_config_yaml(config).encode())
    expect(page.get_by_role("button", name="Сгенерировать расписание", exact=True)).to_be_enabled()
    page.get_by_role("button", name="Сгенерировать расписание", exact=True).click()
    expect(
        page.get_by_text("Текущая версия прошла обязательные проверки", exact=True)
    ).to_be_visible(timeout=30000)
    wait_saved(page)
    before = saved(page)
    assert len(before["config"]["pins"]) == 1
    active = before["active_revisions"][before["selected_period"]]
    schedule = next(r["schedule"] for r in before["revisions"] if r["id"] == active)
    workday = next(day for day in schedule["days"] if "M0" in day["workday"])
    page.get_by_role("tab", name="Редактирование", exact=True).click()
    date_control = (
        page.get_by_test_id("stDateInput")
        .filter(has=page.get_by_text("Дата «Р»", exact=True))
        .locator("input")
    )
    date_control.fill(workday["date"])
    date_control.press("Tab")
    page.get_by_label("Индивидуальные рабочие часы", exact=True).fill("8")
    page.get_by_role("button", name="Назначить «Р» и подтвердить часы", exact=True).click()
    expect(
        page.get_by_text("Текущая версия изменена и требует проверки", exact=True)
    ).to_be_visible(timeout=20000)
    page.get_by_role("button", name="Проверить текущую версию", exact=True).click()
    expect(
        page.get_by_text("Текущая версия прошла обязательные проверки", exact=True)
    ).to_be_visible()
    wait_saved(page)
    before = saved(page)
    with page.expect_download() as download:
        page.get_by_role("button", name="Скачать XLS", exact=True).click()
    assert download.value.suggested_filename.endswith(".xlsx")
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page)["active_revisions"] == before["active_revisions"]
