import json

import pytest
from playwright.sync_api import Page, expect

from duty_schedule.ui.config_io import dump_config_yaml
from duty_schedule.ui.onboarding import OnboardingDraft, apply_city_lists, serialize_draft
from tests.ui.fixtures import journey_config
from tests.ui.test_product_recovery import saved, wait_saved
from tests.ui.test_project_journey import _upload

pytestmark = pytest.mark.ui


def rows(page):
    snapshot = saved(page)
    return (
        snapshot["draft"]["rows"]
        if snapshot.get("kind") == "roster_draft"
        else snapshot["config"]["employees"]
    )


def wait_rows(page, count):
    page.wait_for_function(
        "n => {const id=localStorage.getItem('duty-schedule:last');"
        "const raw=localStorage.getItem('duty-schedule:project:'+id);"
        "if(!raw)return false;const p=JSON.parse(JSON.parse(raw).project);"
        "return (p.draft?.rows||p.config?.employees)?.length===n;}",
        arg=count,
    )
    wait_saved(page)
    page.wait_for_function(
        "document.querySelector('[data-testid=stApp]')?.dataset.testScriptState === 'notRunning'"
    )


def open_cell(page, row, column):
    canvas = page.locator('[data-testid="data-grid-canvas"]:visible').first
    page.wait_for_function(
        "document.querySelector('[data-testid=stApp]')?.dataset.testScriptState === 'notRunning'"
    )
    box = canvas.bounding_box()
    x = box["x"] + 34 + (column + 0.5) * (box["width"] - 34) / 4
    y = box["y"] + 36 + (row + 0.5) * 35
    page.mouse.move(x, y)
    page.evaluate(
        "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    page.mouse.dblclick(x, y, delay=100)


def edit_cell(page, row, column, value):
    open_cell(page, row, column)
    if column == 0:
        field = page.locator(".gdg-input")
        field.fill(value)
        field.press("Enter")
    else:
        dropdown = page.locator('[id^="react-select-"][id$="-input"]')
        expect(dropdown).to_be_visible(timeout=3000)
        if dropdown.get_attribute("aria-expanded") != "true":
            dropdown.press("ArrowDown")
        expect(page.get_by_role("option", name=value, exact=True)).to_be_visible()
        dropdown.fill(value)
        dropdown.press("Enter")
    field = ["name", "city", "schedule_type", "on_duty"][column]
    expected = (
        value
        if column == 0
        else (
            {
                "Москва": "moscow",
                "Хабаровск": "khabarovsk",
                "Гибкий": "flexible",
                "5/2": "5/2",
                "Да": True,
                "Нет": False,
            }.get(value)
        )
    )
    page.wait_for_function(
        "a => {const id=localStorage.getItem('duty-schedule:last');"
        "const p=JSON.parse(JSON.parse(localStorage.getItem('duty-schedule:project:'+id)).project);"
        "const rows=p.draft?.rows||p.config?.employees;return rows?.[a.row]?.[a.field]===a.value;}",
        arg={"row": row, "field": field, "value": expected},
    )
    wait_saved(page)
    page.wait_for_function(
        "document.querySelector('[data-testid=stApp]')?.dataset.testScriptState === 'notRunning'"
    )
    expect(page.locator(f"#glide-cell-{column + 1}-{row}")).to_have_text(value)


def start_roster(page, url, moscow="M0\nM1\nM2\nM3", khabarovsk="K0\nK1"):
    page.set_viewport_size({"width": 1440, "height": 1200})
    page.goto(url, wait_until="networkidle")
    wait_saved(page)
    legacy = apply_city_lists(OnboardingDraft(year=2026, month=4), moscow, khabarovsk)
    _upload(
        page,
        "Открыть черновик состава (.json)",
        "legacy-draft.json",
        serialize_draft(legacy).encode(),
    )
    wait_rows(page, len(legacy.employees))
    expect(page.get_by_role("tab", name="0. Персонал", exact=True)).to_have_count(0)


def all_roles(page, schedule="Гибкий", duty="Да"):
    for index in range(len(rows(page))):
        if schedule != "Не менять":
            edit_cell(page, index, 2, schedule)
        if duty != "Не менять":
            edit_cell(page, index, 3, duty)


def test_empty_start_and_city_lists_create_actual_roster(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    wait_saved(page)
    assert rows(page) == []
    expect(page.get_by_role("tab", name="0. Персонал", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Сохранить настройки", exact=True)).to_have_count(0)
    page.get_by_role("button", name="Добавить строку", exact=True).click()
    wait_rows(page, 1)
    assert rows(page)[0]["name"] == ""
    assert all(rows(page)[0][key] is None for key in ("city", "schedule_type", "on_duty"))
    edit_cell(page, 0, 0, "Иванов, Иван")
    edit_cell(page, 0, 1, "Москва")
    assert rows(page)[0]["name"] == "Иванов, Иван"
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert rows(page)[0]["city"] == "moscow"


def test_schedule_and_duty_are_independent(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url, "M0", "K0")
    edit_cell(page, 0, 2, "5/2")
    edit_cell(page, 0, 3, "Да")
    before = rows(page)
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert rows(page) == before
    assert before[0]["schedule_type"] == "5/2" and before[0]["on_duty"] is True
    page.get_by_label("Год", exact=True).fill("2027")
    page.get_by_label("Год", exact=True).press("Tab")
    page.wait_for_function(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "const p=JSON.parse(JSON.parse(localStorage.getItem('duty-schedule:project:'+id)).project);"
        "return p.draft?.year===2027;}"
    )
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page)["draft"]["year"] == 2027
    assert rows(page) == before


def test_partial_group_roles_and_independent_city_counts(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url, "M0", "K0")
    all_roles(page, "5/2", "Не менять")
    assert all(row["on_duty"] is None for row in rows(page))
    all_roles(page, "Не менять", "Да")
    assert all(row["schedule_type"] == "5/2" and row["on_duty"] is True for row in rows(page))
    assert [row["city"] for row in rows(page)] == ["moscow", "khabarovsk"]
    expect(page.get_by_role("button", name="Сгенерировать расписание", exact=True)).to_have_count(0)


def test_invalid_team_preserves_draft_and_explains_fix(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url, "Один", "")
    all_roles(page, "Гибкий", "Нет")
    expect(
        page.get_by_text("Недостаточно дежурных сотрудников в Москве", exact=False).first
    ).to_be_visible()
    assert rows(page)[0]["name"] == "Один"
    expect(page.get_by_role("button", name="Сгенерировать расписание", exact=True)).to_have_count(0)


def test_partial_draft_reload_and_backup(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url, "M0", "K0")
    all_roles(page, "Гибкий", "Не менять")
    before = saved(page)
    with page.expect_download() as download:
        page.get_by_role("button", name="Сохранить черновик состава", exact=True).click()
    assert download.value.suggested_filename == "roster-draft.json"
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page) == before
    _upload(page, "Открыть черновик состава (.json)", "draft.json", json.dumps(before).encode())
    wait_saved(page)
    assert saved(page) == before
    _upload(page, "Открыть черновик состава (.json)", "bad.json", b"{}", valid=False)
    expect(page.get_by_text("Некорректный файл рабочего проекта", exact=True)).to_be_visible()
    assert saved(page) == before


def test_existing_project_and_yaml_bypass_onboarding_without_loss(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    config = journey_config()
    _upload(page, "Загрузить конфиг (.yaml)", "legacy.yaml", dump_config_yaml(config).encode())
    wait_saved(page)
    before = saved(page)
    assert before["config"]["employees"] == config.model_dump(mode="json")["employees"]
    assert before["config"]["pins"] == config.model_dump(mode="json")["pins"]
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page) == before
    expect(page.get_by_role("tab", name="0. Персонал", exact=True)).to_have_count(0)


def test_onboarding_to_first_month_without_all_cell_pins(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    all_roles(page)
    expect(page.get_by_text("Готовность к расчёту", exact=True)).to_be_visible()
    wait_saved(page)
    before = saved(page)
    ids = [e["employee_id"] for e in before["config"]["employees"]]
    page.get_by_role("tab", name="2. Ограничения", exact=True).click()
    page.get_by_role("button", name="Обновить производственный календарь", exact=True).click()
    expect(page.get_by_text("Календарь 04.2026: offline_test_fixture", exact=False)).to_be_visible()
    page.get_by_role("tab", name="3. История", exact=True).click()
    from io import BytesIO

    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "График дежурств"
    sheet.append(["История марта 2026"])
    sheet.append(["Сотрудник", "Город", *range(1, 32), "Итого"])
    for employee in before["config"]["employees"]:
        sheet.append([employee["name"], employee["city"], *(["—"] * 31)])
    metadata = workbook.create_sheet("__duty_schedule_metadata__")
    metadata.append(
        [
            json.dumps(
                {
                    "format_version": 1,
                    "year": 2026,
                    "month": 3,
                    "employee_ids": {
                        e["name"]: e["employee_id"] for e in before["config"]["employees"]
                    },
                }
            )
        ]
    )
    stream = BytesIO()
    workbook.save(stream)
    page.get_by_test_id("stFileUploader").filter(
        has=page.get_by_text("Загрузить предыдущий график (.xlsx)", exact=True)
    ).locator('input[type="file"]').set_input_files(
        {
            "name": "history.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "buffer": stream.getvalue(),
        }
    )
    expect(page.get_by_text("history.xlsx", exact=False).first).to_be_visible()
    page.get_by_role("tab", name="3. История", exact=True).click()
    expect(page.get_by_role("button", name="Применить историю из XLS", exact=True)).to_be_visible()
    page.get_by_role("button", name="Применить историю из XLS", exact=True).click()
    page.get_by_role("button", name="Сгенерировать расписание", exact=True).click()
    expect(
        page.get_by_text("Текущая версия прошла обязательные проверки", exact=True)
    ).to_be_visible(timeout=40000)
    wait_saved(page)
    before = saved(page)
    assert before["config"]["pins"] == []
    assert [e["employee_id"] for e in before["config"]["employees"]] == ids
    with page.expect_download() as download:
        page.get_by_role("button", name="Скачать XLS", exact=True).click()
    assert download.value.suggested_filename.endswith(".xlsx")
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page)["active_revisions"] == before["active_revisions"]


def test_draft_two_tabs_conflict_preserves_newer_snapshot(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url, "M0", "K0")
    second = page.context.new_page()
    second.goto(streamlit_url, wait_until="networkidle")
    wait_saved(second)
    edit_cell(page, 0, 0, "Первый")
    before = saved(page)
    open_cell(second, 0, 0)
    second.locator(".gdg-input").fill("Другой")
    second.locator(".gdg-input").press("Enter")
    expect(second.get_by_text("Ошибка сохранения:", exact=False)).to_be_visible(timeout=20000)
    assert saved(page) == before
    second.get_by_role("button", name="Сохранить копию в этом браузере", exact=True).click()
    wait_saved(second)
    identity = saved(second)["draft"]["id"]
    assert identity != before["draft"]["id"]
    edit_cell(second, 0, 0, "Копия")
    second.reload(wait_until="networkidle")
    wait_saved(second)
    assert saved(second)["draft"]["id"] == identity
    assert rows(second)[0]["name"] == "Копия"
    second.close()


def test_draft_quota_and_transition_failure_preserve_backup(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url, "M0", "K0")
    before = saved(page)
    page.add_init_script(
        "const originalSetItem=Storage.prototype.setItem;"
        "Storage.prototype.setItem=function(key,value){"
        "if(key.startsWith('duty-schedule:project:'))throw Error('QuotaExceededError');"
        "return originalSetItem.call(this,key,value);};"
    )
    page.reload(wait_until="networkidle")
    wait_saved(page)
    page.get_by_role("button", name="Копировать строку", exact=True).click()
    expect(page.get_by_text("Ошибка сохранения:", exact=False)).to_be_visible(timeout=20000)
    assert saved(page) == before
    expect(page.get_by_role("button", name="Скачать резервный JSON", exact=True)).to_be_visible()


def test_corrupt_draft_recovers_previous_snapshot(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url, "M0", "K0")
    edit_cell(page, 0, 0, "Сохранённый")
    previous = page.evaluate(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "return localStorage.getItem('duty-schedule:project:'+id+':previous');}"
    )
    page.evaluate(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "localStorage.setItem('duty-schedule:project:'+id,'corrupt');}"
    )
    page.reload(wait_until="networkidle")
    expect(page.get_by_text("Восстановлена последняя резервная версия", exact=False)).to_be_visible(
        timeout=20000
    )
    recovered = json.loads(json.loads(previous)["project"])
    expect(page.locator("#glide-cell-1-0")).to_have_text(recovered["draft"]["rows"][0]["name"])
    with page.expect_download() as download:
        page.get_by_role("button", name="Скачать резервный JSON", exact=True).click()
    from pathlib import Path

    assert json.loads(Path(download.value.path()).read_text()) == recovered


def test_draft_rename_and_unset_keep_id_and_other_roles(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url, "M0", "K0")
    edit_cell(page, 0, 2, "Гибкий")
    edit_cell(page, 0, 3, "Да")
    identity = rows(page)[0]["employee_id"]
    edit_cell(page, 0, 0, "Иванов, Иван")
    assert rows(page)[0]["employee_id"] == identity
    assert rows(page)[0]["schedule_type"] == "flexible" and rows(page)[0]["on_duty"] is True


def test_new_project_starts_empty_without_deleting_old_snapshot(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    _upload(
        page, "Загрузить конфиг (.yaml)", "team.yaml", dump_config_yaml(journey_config()).encode()
    )
    wait_saved(page)
    wait_rows(page, 6)
    expect(page.locator("#glide-cell-1-0")).to_have_text("M0")
    previous = saved(page)
    previous_id = previous["id"]
    page.get_by_role("button", name="Новый проект", exact=True).click()
    wait_rows(page, 0)
    assert saved(page)["draft"]["id"] != previous_id
    assert page.evaluate(
        "id => localStorage.getItem('duty-schedule:project:'+id)!==null", previous_id
    )


def test_native_rows_edit_remove_and_reload(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url, "M0", "K0")
    identity = rows(page)[0]["employee_id"]
    edit_cell(page, 0, 0, "Иванов, Иван")
    page.get_by_role("button", name="Удалить строку", exact=True).click()
    wait_rows(page, 1)
    assert rows(page)[0]["employee_id"] != identity
    before = saved(page)
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page) == before
