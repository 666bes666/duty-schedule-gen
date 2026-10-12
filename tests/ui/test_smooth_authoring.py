from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.ui.test_personnel_onboarding import choose, start_roster
from tests.ui.test_product_recovery import saved, wait_saved

pytestmark = pytest.mark.ui


def test_pending_profiles_city_and_reload(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    choose(page, "Кого настроить", "Москва")
    page.get_by_role("button", name="5/2 · дежурит", exact=True).click()
    expect(page.get_by_text("Назначено: 4 · 5/2 · дежурит", exact=True)).to_be_visible()
    remaining = page.get_by_test_id("stMultiSelect").filter(
        has=page.get_by_text("Осталось назначить", exact=True)
    )
    expect(remaining).to_contain_text("K0")
    expect(remaining).not_to_contain_text("M0")
    wait_saved(page)
    before = saved(page)
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page) == before
    page.get_by_role("button", name="Гибкий · дежурит", exact=True).click()
    expect(
        page.get_by_text("Все сотрудники настроены. Можно продолжить подготовку.", exact=True)
    ).to_be_visible()
    wait_saved(page)
    personnel = saved(page)["draft"]["employees"]
    assert all(e["schedule_type"] == "5/2" and e["on_duty"] for e in personnel[:4])
    assert all(e["schedule_type"] == "flexible" and e["on_duty"] for e in personnel[4:])
    page.get_by_role("button", name="Продолжить подготовку", exact=True).click()
    expect(page.get_by_text("Готовность к расчёту", exact=True)).to_be_visible()


def test_ready_navigation_and_advanced_controls(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    page.get_by_role("button", name="Гибкий · дежурит", exact=True).click()
    expect(page.get_by_role("button", name="Продолжить подготовку", exact=True)).to_be_enabled()
    page.get_by_role("button", name="Продолжить подготовку", exact=True).click()
    ready = page.get_by_text("Готовность к расчёту", exact=True)
    expect(ready).to_be_visible()
    tabs = page.get_by_role("tab", name="1. Состав", exact=True)
    assert ready.bounding_box()["y"] < tabs.bounding_box()["y"]
    page.get_by_role("button", name="Открыть «3. История»", exact=True).click()
    expect(page.get_by_role("tab", name="3. История", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    page.get_by_role("tab", name="1. Состав", exact=True).click()
    expect(page.get_by_label("По убыванию", exact=True)).not_to_be_visible()
    page.get_by_text("Дополнительные операции со составом", exact=True).click()
    expect(page.get_by_label("По убыванию", exact=True)).to_be_visible()
    expect(
        page.get_by_label("Диагностическое исследование неполных данных", exact=True)
    ).not_to_be_visible()
    page.get_by_text("Расширенный расчёт", exact=True).click()
    expect(
        page.get_by_label("Диагностическое исследование неполных данных", exact=True)
    ).to_be_visible()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_mobile_and_theme_status(page: Page, streamlit_url: str, theme: str):
    start_roster(page, streamlit_url)
    page.set_viewport_size({"width": 375, "height": 812})
    button = page.get_by_role("button", name="Гибкий · дежурит", exact=True)
    expect(button).to_be_visible()
    assert button.bounding_box()["height"] >= 44
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    button.focus()
    page.keyboard.press("Enter")
    expect(
        page.get_by_text("Все сотрудники настроены. Можно продолжить подготовку.", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="Продолжить подготовку", exact=True).click()
    wait_saved(page)
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
