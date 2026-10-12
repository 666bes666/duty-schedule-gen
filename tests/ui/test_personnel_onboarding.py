import json

import pytest
from playwright.sync_api import Page, expect

from duty_schedule.ui.config_io import dump_config_yaml
from tests.ui.fixtures import journey_config
from tests.ui.test_product_recovery import saved, wait_saved
from tests.ui.test_project_journey import _upload


def choose(page: Page, label: str, value: str):
    group = page.get_by_test_id("stRadio").filter(has=page.get_by_text(label, exact=True))
    group.get_by_text(value, exact=True).click()


def add_native_employee(page: Page, city: str, name: str):
    field = page.get_by_label(f"Новый сотрудник — {city}", exact=True)
    field.fill(name)
    page.get_by_role("button", name=f"Добавить — {city}", exact=True).click()
    expect(field).to_have_value("")
    page.wait_for_function(
        "name => {const id=localStorage.getItem('duty-schedule:last');"
        "const p=JSON.parse(JSON.parse(localStorage.getItem('duty-schedule:project:'+id)).project);"
        "return p.draft?.employees.some(e=>e.name===name);}",
        arg=name.strip(),
    )


def start_roster(page: Page, url: str, moscow="M0\nM1\nM2\nM3", khabarovsk="K0\nK1"):
    page.set_viewport_size({"width": 1440, "height": 2000})
    page.goto(url, wait_until="networkidle")
    wait_saved(page)
    for city, content in (("Москва", moscow), ("Хабаровск", khabarovsk)):
        for name in content.splitlines():
            if name.strip():
                add_native_employee(page, city, name)
    wait_saved(page)
    page.wait_for_function("() => !document.querySelector('[data-stale=\"true\"]')")
    box = page.get_by_test_id("stSelectbox").filter(
        has=page.get_by_text("Месяц подготовки", exact=True)
    )
    control = box.get_by_role("combobox", name="Месяц подготовки", exact=True)
    control.press("ArrowDown")
    option = page.get_by_role("option", name="Апрель", exact=True)
    expect(option).to_be_visible()
    option.click()
    expect(control).to_have_value("Апрель")
    page.get_by_label("Год подготовки", exact=True).fill("2026")
    page.get_by_role("button", name="Перейти к настройке состава", exact=True).click()
    expect(page.get_by_text("Не настроено:", exact=False).first).to_be_visible()
    page.wait_for_function(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "const r=localStorage.getItem('duty-schedule:project:'+id);"
        "return r && JSON.parse(JSON.parse(r).project).draft?.stage==='roles';}"
    )


def all_roles(page: Page, schedule="Гибкий", duty="Да"):
    expander = page.get_by_test_id("stExpander").filter(
        has=page.get_by_text("Назначить только график или дежурства", exact=True)
    )
    if expander.locator("details").get_attribute("open") is None:
        expander.locator("summary").click()
    if not page.get_by_label("Все оставшиеся", exact=True).is_checked():
        page.get_by_text("Все оставшиеся", exact=True).click()
    choose(page, "График группы", schedule)
    choose(page, "Дежурства группы", duty)
    page.get_by_role("button", name="Применить к группе", exact=True).click()
    expect(page.get_by_label("Все оставшиеся", exact=True)).not_to_be_checked()


@pytest.mark.ui
def test_empty_start_and_city_lists_create_actual_roster(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    wait_saved(page)
    assert saved(page)["draft"]["employees"] == []
    expect(page.get_by_label("Новый сотрудник — Москва", exact=True)).to_have_value("")
    expect(page.get_by_label("Новый сотрудник — Хабаровск", exact=True)).to_have_value("")
    expect(page.get_by_role("button", name="Сгенерировать расписание", exact=True)).to_have_count(0)
    start_roster(page, streamlit_url, " Иванов, Иван \n\nПётр", "")
    assert [e["name"] for e in saved(page)["draft"]["employees"]] == ["Иванов, Иван", "Пётр"]
    assert all(
        e["on_duty"] is None and e["schedule_type"] is None
        for e in saved(page)["draft"]["employees"]
    )


@pytest.mark.ui
def test_schedule_and_duty_are_independent(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    page.get_by_text("Изменить персональные настройки", exact=True).click()
    choose(page, "График сотрудника", "5/2")
    choose(page, "Участие в дежурствах", "Да")
    page.get_by_role("button", name="Применить сотруднику", exact=True).click()
    page.wait_for_function(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "const p=JSON.parse(JSON.parse(localStorage.getItem("
        "'duty-schedule:project:'+id)).project);"
        "return p.draft?.employees[0].schedule_type==='5/2' "
        "&& p.draft.employees[0].on_duty===true;}"
    )
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page)["draft"]["employees"][0]["on_duty"] is True
    assert saved(page)["draft"]["employees"][0]["schedule_type"] == "5/2"


@pytest.mark.ui
def test_partial_group_roles_and_independent_city_counts(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    all_roles(page, "5/2", "Не менять")
    expect(page.get_by_role("button", name="Продолжить подготовку", exact=True)).to_be_disabled()
    expect(page.get_by_text("участие в дежурствах", exact=False).first).to_be_visible()
    all_roles(page, "Не менять", "Да")
    page.get_by_text("Посмотреть весь состав", exact=True).click()
    expect(
        page.get_by_text(
            "Москва: всего 4; 5/2 — 4; гибкий — 0; дежурит — 4; не настроено — 0", exact=True
        )
    ).to_be_visible()
    expect(page.get_by_role("button", name="Продолжить подготовку", exact=True)).to_be_enabled()


@pytest.mark.ui
def test_invalid_team_preserves_draft_and_explains_fix(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url, "Один", "")
    all_roles(page, "Гибкий", "Нет")
    page.get_by_role("button", name="Продолжить подготовку", exact=True).click()
    expect(
        page.get_by_text("Недостаточно дежурных сотрудников в Москве", exact=False)
    ).to_be_visible()
    assert saved(page)["kind"] == "personnel_draft"
    assert saved(page)["draft"]["employees"][0]["name"] == "Один"
    expect(page.get_by_role("button", name="Сгенерировать расписание", exact=True)).to_have_count(0)


@pytest.mark.ui
def test_partial_draft_reload_and_backup(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    all_roles(page, "Гибкий", "Не менять")
    page.wait_for_function(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "return JSON.parse(JSON.parse(localStorage.getItem("
        "'duty-schedule:project:'+id)).project).draft?.employees"
        ".every(e=>e.schedule_type==='flexible');}"
    )
    before = saved(page)
    with page.expect_download() as download:
        page.get_by_role("button", name="Сохранить подготовку персонала", exact=True).click()
    assert download.value.suggested_filename == "personnel-draft.json"
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page) == before
    _upload(page, "Открыть подготовку персонала (.json)", "draft.json", json.dumps(before).encode())
    wait_saved(page)
    assert saved(page) == before
    page.get_by_test_id("stFileUploader").filter(
        has=page.get_by_text("Открыть подготовку персонала (.json)", exact=True)
    ).locator('input[type="file"]').set_input_files(
        {"name": "bad.json", "mimeType": "application/json", "buffer": b"{}"}
    )
    expect(page.get_by_text("validation error", exact=False)).to_be_visible()
    assert saved(page) == before


@pytest.mark.ui
def test_existing_project_and_yaml_bypass_onboarding_without_loss(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    config = journey_config()
    _upload(page, "Загрузить конфиг (.yaml)", "legacy.yaml", dump_config_yaml(config).encode())
    expect(page.get_by_text("Готовность к расчёту", exact=True)).to_be_visible()
    wait_saved(page)
    before = saved(page)
    assert before["config"]["employees"] == config.model_dump(mode="json")["employees"]
    assert before["config"]["pins"] == config.model_dump(mode="json")["pins"]
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page) == before
    expect(page.get_by_label("Новый сотрудник — Москва", exact=True)).to_have_count(0)


@pytest.mark.ui
def test_onboarding_to_first_month_without_all_cell_pins(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    all_roles(page)
    page.get_by_role("button", name="Продолжить подготовку", exact=True).click()
    expect(page.get_by_text("Готовность к расчёту", exact=True)).to_be_visible()
    wait_saved(page)
    before = saved(page)
    ids = [e["employee_id"] for e in before["config"]["employees"]]
    page.get_by_role("tab", name="2. Ограничения", exact=True).click()
    page.get_by_role("button", name="Обновить производственный календарь", exact=True).click()
    page.wait_for_function(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "return JSON.parse(JSON.parse(localStorage.getItem("
        "'duty-schedule:project:'+id)).project).config?.production_calendar!==null;}"
    )
    expect(page.get_by_text("Календарь 04.2026: offline_test_fixture", exact=False)).to_be_visible()
    page.wait_for_function("() => !document.querySelector('[data-stale=\"true\"]')")
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


@pytest.mark.ui
def test_draft_two_tabs_conflict_preserves_newer_snapshot(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    second = page.context.new_page()
    second.goto(streamlit_url, wait_until="networkidle")
    wait_saved(second)
    all_roles(page, "Гибкий", "Не менять")
    page.wait_for_function(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "return JSON.parse(JSON.parse(localStorage.getItem("
        "'duty-schedule:project:'+id)).project).draft.employees"
        ".every(e=>e.schedule_type==='flexible');}"
    )
    before = saved(page)
    all_roles(second, "5/2", "Не менять")
    expect(second.get_by_text("Ошибка сохранения:", exact=False)).to_be_visible(timeout=20000)
    assert saved(page) == before
    second.close()


@pytest.mark.ui
def test_draft_quota_and_transition_failure_preserve_backup(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    all_roles(page)
    page.wait_for_function(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "return JSON.parse(JSON.parse(localStorage.getItem("
        "'duty-schedule:project:'+id)).project).draft.employees"
        ".every(e=>e.schedule_type==='flexible' && e.on_duty===true);}"
    )
    before = saved(page)
    page.add_init_script(
        "const originalSetItem=Storage.prototype.setItem;"
        "Storage.prototype.setItem=function(key,value){"
        "if(key.startsWith('duty-schedule:project:'))throw Error('QuotaExceededError');"
        "return originalSetItem.call(this,key,value);};"
    )
    page.reload(wait_until="networkidle")
    wait_saved(page)
    page.get_by_role("button", name="Продолжить подготовку", exact=True).click()
    expect(page.get_by_text("Ошибка сохранения:", exact=False)).to_be_visible(timeout=20000)
    assert saved(page) == before
    expect(page.get_by_role("button", name="Скачать резервный JSON", exact=True)).to_be_visible()
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page) == before
    expect(page.get_by_role("button", name="Продолжить подготовку", exact=True)).to_be_enabled()


@pytest.mark.ui
def test_corrupt_draft_recovers_previous_snapshot(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    all_roles(page, "Гибкий", "Не менять")
    page.wait_for_function(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "return JSON.parse(JSON.parse(localStorage.getItem("
        "'duty-schedule:project:'+id)).project).draft.employees"
        ".every(e=>e.schedule_type==='flexible');}"
    )
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
    expect(page.get_by_text("Не настроено:", exact=False).first).to_be_visible()
    assert (
        page.evaluate(
            "() => {const id=localStorage.getItem('duty-schedule:last');"
            "return localStorage.getItem('duty-schedule:project:'+id+':previous');}"
        )
        == previous
    )


@pytest.mark.ui
def test_draft_rename_and_unset_keep_id_and_other_roles(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    all_roles(page)
    page.get_by_text("Изменить персональные настройки", exact=True).click()
    page.get_by_label("Имя сотрудника", exact=True).fill("Иванов, Иван")
    choose(page, "График сотрудника", "Не настроено")
    page.get_by_role("button", name="Применить сотруднику", exact=True).click()
    page.wait_for_function(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "const p=JSON.parse(JSON.parse(localStorage.getItem("
        "'duty-schedule:project:'+id)).project);"
        "return p.draft.employees[0].name==='Иванов, Иван';}"
    )
    first = saved(page)["draft"]["employees"][0]
    assert first["schedule_type"] is None
    assert first["on_duty"] is True
    expect(page.get_by_role("button", name="Продолжить подготовку", exact=True)).to_be_disabled()


@pytest.mark.ui
def test_new_project_starts_empty_without_deleting_old_snapshot(page: Page, streamlit_url: str):
    page.goto(streamlit_url, wait_until="networkidle")
    _upload(
        page, "Загрузить конфиг (.yaml)", "old.yaml", dump_config_yaml(journey_config()).encode()
    )
    wait_saved(page)
    old = saved(page)
    page.get_by_role("button", name="Новый проект", exact=True).click()
    expect(page.get_by_label("Новый сотрудник — Москва", exact=True)).to_have_value("")
    wait_saved(page)
    page.wait_for_function(
        "old => localStorage.getItem('duty-schedule:last') !== old", arg=old["id"]
    )
    assert saved(page)["draft"]["employees"] == []
    assert (
        page.evaluate(
            "id => JSON.parse(JSON.parse(localStorage.getItem("
            "'duty-schedule:project:'+id)).project)",
            old["id"],
        )
        == old
    )


@pytest.mark.ui
def test_native_rows_edit_remove_and_reload(page: Page, streamlit_url: str):
    start_roster(page, streamlit_url)
    all_roles(page)
    page.get_by_role("tab", name="0. Персонал", exact=True).click()
    expect(page.locator("textarea")).to_have_count(0)
    before = saved(page)["draft"]
    field = page.get_by_label("Имя — M0", exact=True)
    form = page.get_by_test_id("stForm").filter(has=field)
    field.fill("Иванов, Иван")
    form.get_by_role("button", name="Сохранить имя", exact=True).click()
    expect(page.get_by_label("Имя — Иванов, Иван", exact=True)).to_be_visible()
    page.wait_for_function(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "return JSON.parse(JSON.parse(localStorage.getItem('duty-schedule:project:'+id)).project)"
        ".draft.employees[0].name==='Иванов, Иван';}"
    )
    first = saved(page)["draft"]["employees"][0]
    assert first["employee_id"] == before["employees"][0]["employee_id"]
    assert first["on_duty"] is True
    assert first["schedule_type"] == "flexible"
    page.get_by_label("Новый сотрудник — Хабаровск", exact=True).fill("Иванов, Иван")
    page.get_by_role("button", name="Добавить — Хабаровск", exact=True).click()
    expect(page.get_by_text("уже внесён в персонал", exact=False)).to_be_visible()
    assert len(saved(page)["draft"]["employees"]) == 6
    row = page.get_by_test_id("stForm").filter(has=page.get_by_label("Имя — K1", exact=True))
    row.get_by_role("button", name="Удалить", exact=True).click()
    expect(page.get_by_label("Имя — K1", exact=True)).to_have_count(0)
    page.wait_for_function(
        "() => {const id=localStorage.getItem('duty-schedule:last');"
        "return JSON.parse(JSON.parse(localStorage.getItem('duty-schedule:project:'+id)).project)"
        ".draft.employees.length===5;}"
    )
    before_reload = saved(page)
    page.reload(wait_until="networkidle")
    wait_saved(page)
    assert saved(page) == before_reload
    expect(page.get_by_label("Имя — Иванов, Иван", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="Хабаровск · 1", exact=True)).to_be_visible()
