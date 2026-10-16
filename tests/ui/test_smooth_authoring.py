from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from duty_schedule.models import Schedule
from duty_schedule.project import add_revision, new_project, serialize_project
from tests.ui.fixtures import journey_config, journey_days
from tests.ui.test_personnel_onboarding import edit_cell, rows, start_roster, wait_rows
from tests.ui.test_product_recovery import saved, wait_saved
from tests.ui.test_project_journey import _upload

pytestmark = pytest.mark.ui


def test_pending_profiles_city_and_reload(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url, "M0", "K0")
    edit_cell(page, 0, 2, "5/2")
    edit_cell(page, 0, 3, "Да")
    identity = rows(page)[0]["employee_id"]
    page.get_by_role("button", name="Копировать строку", exact=True).click()
    wait_rows(page, 3)
    copied = rows(page)[-1]
    assert copied["name"] == "" and copied["employee_id"] != identity
    assert copied["city"] == "moscow" and copied["schedule_type"] == "5/2"
    assert copied["on_duty"] is True
    edit_cell(page, 2, 0, "Новый")
    page.get_by_role("button", name="Копировать строку", exact=True).click()
    wait_rows(page, 4)
    assert len({row["employee_id"] for row in rows(page)}) == 4
    before = saved(page)
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page) == before


def test_ready_navigation_and_advanced_controls(page: Page, streamlit_url: str):
    page.set_viewport_size({"width": 1440, "height": 1800})
    page.goto(streamlit_url, wait_until="networkidle")
    config = journey_config()
    project = add_revision(new_project(config), Schedule(config=config, days=journey_days(config)))
    _upload(page, "Открыть рабочий проект (.json)", "ready.json", serialize_project(project))
    wait_saved(page)
    expect(page.get_by_role("button", name="Скачать XLS", exact=True)).to_be_visible()
    page.get_by_role("button", name="Копировать строку", exact=True).click()
    wait_rows(page, 7)
    expect(page.get_by_role("button", name="Сгенерировать расписание", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="Скачать XLS", exact=True)).to_have_count(0)
    page.get_by_text("Расширенный расчёт", exact=True).click()
    page.get_by_text("Диагностическое исследование неполных данных", exact=True).click()
    expect(page.get_by_role("button", name="Сгенерировать расписание", exact=True)).to_be_disabled()
    edit_cell(page, 6, 0, "Новый")
    page.get_by_role("button", name="Открыть «3. История»", exact=True).click()
    expect(page.get_by_role("tab", name="3. История", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    page.get_by_role("tab", name="1. Состав", exact=True).click()
    before = rows(page)
    page.get_by_text("Показать особые условия", exact=True).click()
    page.get_by_text("Показать особые условия", exact=True).click()
    assert rows(page) == before


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_mobile_and_theme_status(page: Page, streamlit_url: str, theme: str):
    start_roster(page, streamlit_url, "M0", "K0")
    page.set_viewport_size({"width": 375, "height": 812})
    button = page.get_by_role("button", name="Добавить строку", exact=True)
    expect(button).to_be_visible()
    assert button.bounding_box()["height"] >= 44
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    button.focus()
    page.keyboard.press("Enter")
    wait_rows(page, 3)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    html = (
        Path(__file__).resolve().parents[2] / "src/duty_schedule/ui/autosave_component/index.html"
    ).read_text()
    harness = page.context.new_page()
    harness.set_content("<iframe id='bridge'></iframe>")
    harness.locator("iframe").evaluate("(el, html) => el.srcdoc = html", html)
    frame = harness.frame_locator("iframe")
    expect(frame.locator("#status")).to_have_text("Сохранение идёт…")
    palette = (
        {"textColor": "#fafafa", "backgroundColor": "#0e1117"}
        if theme == "dark"
        else {"textColor": "#31333f", "backgroundColor": "#ffffff"}
    )
    harness.evaluate(
        "theme => document.querySelector('iframe').contentWindow.postMessage("
        "{type:'streamlit:render',theme,args:{blocked:true}}, '*')",
        palette,
    )
    expect(frame.locator("#status")).to_have_text("Ошибка сохранения; доступна резервная копия")
    colors = frame.locator("body").evaluate(
        "el => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]"
    )
    assert colors == (
        ["rgb(250, 250, 250)", "rgb(14, 17, 23)"]
        if theme == "dark"
        else ["rgb(49, 51, 63)", "rgb(255, 255, 255)"]
    )
    harness.close()
