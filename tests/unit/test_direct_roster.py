import json
from datetime import date

import pytest

from duty_schedule.models import City, ScheduleType, VacationPeriod
from duty_schedule.project import new_project, serialize_project
from duty_schedule.ui.onboarding import (
    OnboardingDraft,
    apply_city_lists,
    assign_roles,
    restore_snapshot,
    serialize_draft,
    storage_snapshot,
)
from duty_schedule.ui.roster import (
    RosterDraft,
    RosterRow,
    apply_delta,
    copy_row,
    from_project,
    initialize_roster,
    load_roster,
    roster_config,
    row_issues,
    serialize_roster,
)
from tests.ui.fixtures import journey_config


def test_copy_preserves_columns_with_new_identity():
    project = new_project(journey_config())
    source = project.config.employees[0]
    source.vacations = [VacationPeriod(start=date(2026, 4, 3), end=date(2026, 4, 3))]
    source.sick_leaves = [VacationPeriod(start=date(2026, 4, 4), end=date(2026, 4, 4))]
    source.unavailable_dates = [date(2026, 4, 5)]
    source.days_off_weekly = [6]
    draft = from_project(project)
    draft.rows[0].always_on_duty = True
    draft.rows[0].morning_only = True
    draft.rows[0].max_consecutive_working = 5
    copied = copy_row(draft, draft.rows[0].employee_id)
    again = copy_row(copied, draft.rows[0].employee_id)
    assert len({row.employee_id for row in again.rows}) == len(again.rows)
    assert copied.rows[-1].name == ""
    assert copied.rows[-1].model_dump(exclude={"employee_id", "name"}) == draft.rows[0].model_dump(
        exclude={"employee_id", "name"}
    )
    assert len(draft.rows) == len(project.config.employees)
    with pytest.raises(ValueError):
        copy_row(draft, "unknown")
    copied.rows[-1].name = "Другой"
    config = roster_config(copied, project)
    clone = config.employees[-1]
    assert clone.always_on_duty and clone.morning_only
    assert clone.vacations == clone.sick_leaves == clone.unavailable_dates == []
    assert clone.days_off_weekly == []
    assert all(pin.employee_name != clone.name for pin in config.pins)
    assert all(record.employee_id != clone.employee_id for record in config.carry_over)


def test_incomplete_duplicate_and_invalid_rows_persist():
    project = new_project(journey_config())
    draft = from_project(project)
    empty = copy_row(draft, draft.rows[0].employee_id)
    duplicate = draft.model_copy(deep=True)
    duplicate.rows[1].name = duplicate.rows[0].name
    newline = draft.model_copy(deep=True)
    newline.rows[0].name = "Имя\nещё"
    for invalid in (empty, duplicate, newline):
        assert load_roster(serialize_roster(invalid, project))[0] == invalid
        with pytest.raises(ValueError):
            roster_config(invalid, project)
    incompatible = from_project(project)
    incompatible.rows[0].always_on_duty = True
    assert row_issues(incompatible)
    assert load_roster(serialize_roster(incompatible, project))[0] == incompatible
    with pytest.raises(ValueError):
        roster_config(incompatible, project)
    assert RosterRow().city is None and RosterRow().on_duty is None
    assert row_issues(RosterDraft(year=2026, month=4))


def test_snapshot_and_legacy_migration_are_atomic():
    legacy = apply_city_lists(OnboardingDraft(year=2026, month=4), "M0\nM1", "K0")
    legacy = assign_roles(legacy, [legacy.employees[0].employee_id], ScheduleType.FIVE_TWO, True)
    state = {}
    restore_snapshot(state, serialize_draft(legacy))
    initialize_roster(state)
    assert state["roster_draft"].id == legacy.id
    assert state["roster_draft"].rows[0].on_duty is True
    assert state["roster_draft"].rows[1].on_duty is None
    before = storage_snapshot(state)
    for raw in ("{}", '{"kind":"roster_draft","version":2}', '{"kind":"x"}'):
        with pytest.raises(ValueError):
            restore_snapshot(state, raw)
        assert storage_snapshot(state) == before
    restored = {}
    restore_snapshot(restored, before[0])
    assert restored["roster_draft"] == state["roster_draft"]
    project = new_project(journey_config())
    restore_snapshot(restored, serialize_project(project))
    initialize_roster(restored)
    assert roster_config(restored["roster_draft"], restored["project"]) == project.config
    assert storage_snapshot(restored)[0] == serialize_project(project).decode()
    invalid = copy_row(restored["roster_draft"], project.config.employees[0].employee_id)
    raw = json.loads(serialize_roster(invalid, project))
    raw["project"]["id"] = "different"
    with pytest.raises(ValueError):
        restore_snapshot(restored, json.dumps(raw))
    assert restored["project"] == project


def test_valid_edit_preserves_base_and_dates_by_id():
    project = new_project(journey_config())
    original = project.config.employees[0]
    original.vacations = [VacationPeriod(start=date(2026, 4, 3), end=date(2026, 4, 3))]
    draft = from_project(project)
    draft.rows[0].name = "Новое имя"
    changed = roster_config(draft, project)
    assert changed.employees[0].employee_id == original.employee_id
    assert changed.employees[0].vacations == original.vacations
    assert changed.production_calendar == project.config.production_calendar
    assert all(pin.employee_name != original.name for pin in changed.pins)
    assert changed.carry_over[0].employee_name == "Новое имя"
    assert project.config.employees[0].name == original.name
    draft.month = 5
    assert roster_config(draft, project).production_calendar is None
    assert project.config.month == 4
    assert original.vacations[0].start == date(2026, 4, 3)


def test_cumulative_delta_keeps_ids_and_deletion_is_exact():
    seed = RosterDraft(year=2026, month=4, rows=[RosterRow(name="Первый")])
    added_ids = {}
    delta = {
        "edited_rows": {0: {"Имя": "Изменён", "ID": "forged"}},
        "added_rows": [{"Имя": "Второй", "Город": "Москва"}],
    }
    first = apply_delta(seed, delta, added_ids)
    second = apply_delta(seed, delta, added_ids)
    assert first == second
    assert first.rows[0].employee_id == seed.rows[0].employee_id
    assert first.rows[1].city == City.MOSCOW
    assert first.rows[1].schedule_type is None and first.rows[1].on_duty is None
    removed = apply_delta(first, {"deleted_rows": [0]}, {})
    assert removed.rows == [first.rows[1]]
    assert seed.rows[0].name == "Первый"


def test_forked_draft_keeps_identity_on_next_edit(monkeypatch):
    from types import SimpleNamespace

    from duty_schedule.ui import components

    project = new_project(journey_config())
    seed = copy_row(from_project(project), project.config.employees[0].employee_id)
    fork = project.model_copy(update={"id": "forked"}, deep=True)
    current = seed.model_copy(update={"id": fork.id, "month": 5}, deep=True)
    state = {
        "project": fork,
        "roster_draft": current,
        "ui_0_roster_table_False": {"edited_rows": {0: {"Имя": "Изменён"}}},
    }
    monkeypatch.setattr(components, "st", SimpleNamespace(session_state=state))
    components._roster_changed(seed, "ui_0_roster_table_False")
    snapshot, identity = storage_snapshot(state)
    restored, base = load_roster(snapshot)
    assert identity == restored.id == base.id == "forked"
    assert restored.month == 5
    assert restored.rows[0].name == "Изменён"
    assert restored.rows[-1].name == ""


def test_stale_editor_callbacks_cannot_change_imported_roster(monkeypatch):
    from types import SimpleNamespace

    from duty_schedule.ui import components

    project = new_project(journey_config())
    imported = from_project(project)
    old = RosterDraft(year=2026, month=11)
    state = {
        "project": project,
        "roster_draft": imported,
        "ui_epoch": 1,
        "ui_0_roster_month": 11,
        "ui_0_roster_year": 2026,
        "ui_0_roster_table_False": {"edited_rows": {}, "added_rows": [{"Имя": "Старый"}]},
    }
    monkeypatch.setattr(components, "st", SimpleNamespace(session_state=state))
    components._roster_period_changed("ui_0_roster_month", "ui_0_roster_year")
    components._roster_changed(old, "ui_0_roster_table_False")
    assert state["roster_draft"] == imported
    assert state["project"] == project
    state.update(ui_1_roster_month=5, ui_1_roster_year=2026)
    components._roster_period_changed("ui_1_roster_month", "ui_1_roster_year")
    assert state["roster_draft"].month == state["project"].config.month == 5
    assert state["project"].config.production_calendar is None
