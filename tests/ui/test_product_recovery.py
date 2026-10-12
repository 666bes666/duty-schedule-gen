from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from duty_schedule.models import Schedule
from duty_schedule.project import add_revision, new_project, serialize_project
from duty_schedule.ui.config_io import dump_config_yaml
from tests.ui.fixtures import journey_config, journey_days
from tests.ui.test_project_journey import _upload


def wait_saved(page: Page):
    expect(
        page.frame_locator('iframe[title="duty_schedule.ui.autosave.duty_autosave"]').get_by_text(
            "Сохранено в этом браузере", exact=True
        )
    ).to_be_visible(timeout=20000)
    heading = page.get_by_role("heading", name=re.compile("текущая версия"))
    if heading.count():
        expected = heading.inner_text().split()[-1]
        page.wait_for_function(
            "prefix => { const id=localStorage.getItem('duty-schedule:last'); "
            "const key='duty-schedule:project:'+id; "
            "const raw=localStorage.getItem(key); "
            "if (!raw) return false; const p=JSON.parse(JSON.parse(raw).project); "
            "return (p.active_revisions[p.selected_period]||'').startsWith(prefix); }",
            arg=expected,
        )


def saved(page: Page):
    return page.evaluate(
        "JSON.parse(JSON.parse(localStorage.getItem('duty-schedule:project:'+localStorage.getItem('duty-schedule:last'))).project)"
    )


@pytest.mark.ui
def test_browser_reload_restores_current_project_and_hours(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    config = journey_config()
    project = add_revision(new_project(config), Schedule(config=config, days=journey_days(config)))
    _upload(page, "Открыть рабочий проект (.json)", "recovery.json", serialize_project(project))
    wait_saved(page)
    before = saved(page)
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page) == before
    expect(
        page.get_by_text("Текущая версия прошла обязательные проверки", exact=True)
    ).to_be_visible()


@pytest.mark.ui
def test_imported_history_unchanged_save_preserves_every_employee(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    config = journey_config()
    config.carry_over[0].consecutive_off = 4
    config.carry_over[0].source = "xls"
    _upload(page, "Загрузить конфиг (.yaml)", "history.yaml", dump_config_yaml(config).encode())
    wait_saved(page)
    before = saved(page)["config"]["carry_over"]
    page.get_by_role("tab", name="3. История", exact=True).click()
    page.get_by_role("button", name="Сохранить исходную историю", exact=True).click()
    wait_saved(page)
    assert saved(page)["config"]["carry_over"] == before


@pytest.mark.ui
def test_two_tabs_do_not_silently_overwrite_newer_revision(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    _upload(
        page, "Загрузить конфиг (.yaml)", "one.yaml", dump_config_yaml(journey_config()).encode()
    )
    wait_saved(page)
    second = page.context.new_page()
    second.goto(streamlit_url, wait_until="networkidle")
    wait_saved(second)
    config = journey_config()
    config.seed = 77
    _upload(page, "Загрузить конфиг (.yaml)", "two.yaml", dump_config_yaml(config).encode())
    wait_saved(page)
    before = saved(page)
    config.seed = 88
    _upload(second, "Загрузить конфиг (.yaml)", "three.yaml", dump_config_yaml(config).encode())
    expect(second.get_by_text("Ошибка сохранения:", exact=False)).to_be_visible(timeout=20000)
    assert saved(page) == before
    second.close()


@pytest.mark.ui
def test_corrupt_and_refused_storage_preserve_snapshot(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    wait_saved(page)
    before = page.evaluate(
        "localStorage.getItem('duty-schedule:project:'+localStorage.getItem('duty-schedule:last'))"
    )
    page.add_init_script("Storage.prototype.setItem=function(){throw Error('QuotaExceededError')}")
    page.reload(wait_until="networkidle")
    expect(page.get_by_text("Готовность к расчёту", exact=True)).to_be_visible(timeout=20000)
    config = journey_config()
    config.seed = 11
    _upload(page, "Загрузить конфиг (.yaml)", "quota.yaml", dump_config_yaml(config).encode())
    expect(page.get_by_text("Ошибка сохранения:", exact=False)).to_be_visible(timeout=20000)
    assert (
        page.evaluate(
            "localStorage.getItem('duty-schedule:project:'+localStorage.getItem('duty-schedule:last'))"
        )
        == before
    )


@pytest.mark.ui
def test_corrupt_record_preserves_last_valid_copy(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    wait_saved(page)
    _upload(
        page, "Загрузить конфиг (.yaml)", "good.yaml", dump_config_yaml(journey_config()).encode()
    )
    wait_saved(page)
    config = journey_config()
    config.seed = 13
    _upload(page, "Загрузить конфиг (.yaml)", "new.yaml", dump_config_yaml(config).encode())
    wait_saved(page)
    backup = page.evaluate(
        "localStorage.getItem('duty-schedule:project:'+localStorage.getItem('duty-schedule:last')+':previous')"
    )
    assert backup
    page.evaluate(
        "localStorage.setItem('duty-schedule:project:'+localStorage.getItem('duty-schedule:last'),'corrupt')"
    )
    page.reload(wait_until="networkidle")
    expect(page.get_by_text("Ошибка сохранения:", exact=False)).to_be_visible(timeout=20000)
    assert (
        page.evaluate(
            "localStorage.getItem('duty-schedule:project:'+localStorage.getItem('duty-schedule:last')+':previous')"
        )
        == backup
    )
    expect(page.get_by_role("button", name="Скачать резервный JSON", exact=True)).to_be_visible()


@pytest.mark.ui
def test_opening_existing_other_project_updates_last_pointer(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    first = new_project(journey_config())
    second = new_project(journey_config())
    _upload(page, "Открыть рабочий проект (.json)", "second.json", serialize_project(second))
    wait_saved(page)
    _upload(page, "Открыть рабочий проект (.json)", "first.json", serialize_project(first))
    page.wait_for_function("id => localStorage.getItem('duty-schedule:last')===id", arg=first.id)
    page.reload(wait_until="networkidle")
    wait_saved(page)
    _upload(page, "Открыть рабочий проект (.json)", "second-again.json", serialize_project(second))
    page.wait_for_function("id => localStorage.getItem('duty-schedule:last')===id", arg=second.id)
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page)["id"] == second.id


@pytest.mark.ui
def test_unsubmitted_form_is_not_reported_as_saved(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    _upload(
        page, "Загрузить конфиг (.yaml)", "draft.yaml", dump_config_yaml(journey_config()).encode()
    )
    wait_saved(page)
    before = saved(page)
    page.get_by_label("Год", exact=True).fill("2027")
    component = page.frame_locator('iframe[title="duty_schedule.ui.autosave.duty_autosave"]')
    expect(component.get_by_text("Есть неприменённые правки формы", exact=True)).to_be_visible()
    assert saved(page) == before
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page) == before


@pytest.mark.ui
def test_unavailable_log_is_not_reported_as_no_changes(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    config = journey_config()
    project = add_revision(new_project(config), Schedule(config=config, days=journey_days(config)))
    _upload(page, "Открыть рабочий проект (.json)", "no-log.json", serialize_project(project))
    page.get_by_role("tab", name="Лог оптимизации", exact=True).click()
    expect(page.get_by_text("log_unavailable:", exact=False)).to_be_visible(timeout=20000)
    expect(page.get_by_text("Оптимизация: no_changes", exact=False)).to_have_count(0)
