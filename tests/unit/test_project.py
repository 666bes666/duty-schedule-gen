import json
from datetime import date

import pytest

from duty_schedule.models import (
    City,
    Config,
    DaySchedule,
    Employee,
    Schedule,
    ScheduleType,
    ShiftType,
)
from duty_schedule.project import (
    ExportBlockedError,
    add_revision,
    apply_assignments,
    current_schedule,
    ensure_exportable,
    load_project,
    new_project,
    serialize_project,
    update_config,
)


@pytest.fixture
def default_config() -> Config:
    employees = [
        Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(1, 7)
    ] + [
        Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(1, 3)
    ]
    return Config(month=3, year=2026, employees=employees)


def test_project_round_trip_preserves_revisions_and_hours(default_config: Config) -> None:
    schedule = Schedule(
        config=default_config,
        days=[DaySchedule(date=date(2026, 3, 2), workday=["М1"], workday_hours={"М1": 3})],
    )
    project = add_revision(new_project(default_config), schedule)
    restored = load_project(serialize_project(project))
    assert restored.active_revisions == project.active_revisions
    assert restored.revisions[0].schedule.days[0].workday_hours == {"М1": 3}
    assert current_schedule(restored).status == "diagnostic"


def test_edit_pins_both_changed_participants(default_config: Config) -> None:
    day = date(2026, 3, 2)
    original = Schedule(
        config=default_config,
        days=[DaySchedule(date=day, morning=["М1"], day_off=["М2"])],
    )
    project = add_revision(new_project(default_config), original)
    changed = apply_assignments(project, [DaySchedule(date=day, morning=["М2"], day_off=["М1"])])
    current = current_schedule(changed)
    assert current.status == "draft"
    assert len(changed.revisions) == 2
    assert original.days[0].morning == ["М1"]
    assert {(p.employee_name, p.shift) for p in current.config.pins} == {
        ("М1", ShiftType.DAY_OFF),
        ("М2", ShiftType.MORNING),
    }


def test_forged_ready_status_does_not_allow_export(default_config: Config) -> None:
    forged = Schedule(config=default_config, days=[], status="ready")
    with pytest.raises(ExportBlockedError) as exc:
        ensure_exportable(forged)
    assert exc.value.diagnostics


def test_load_rechecks_saved_ready_status(default_config: Config) -> None:
    project = add_revision(new_project(default_config), Schedule(config=default_config, days=[]))
    data = json.loads(serialize_project(project))
    data["revisions"][0]["schedule"]["status"] = "ready"
    restored = load_project(json.dumps(data))
    assert current_schedule(restored).status == "diagnostic"


def test_invalid_project_cannot_replace_existing(default_config: Config) -> None:
    project = new_project(default_config)
    before = serialize_project(project)
    with pytest.raises(ValueError):
        load_project(b'{"format_version": 99}')
    assert serialize_project(project) == before


def test_changed_month_invalidates_later_active_revision(default_config: Config) -> None:
    project = add_revision(new_project(default_config), Schedule(config=default_config, days=[]))
    april = default_config.model_copy(update={"month": 4})
    project = add_revision(project, Schedule(config=april, days=[]))
    project.selected_period = "2026-03"
    updated = apply_assignments(project, [])
    updated.selected_period = "2026-04"
    assert any(d.code == "previous_revision_changed" for d in current_schedule(updated).diagnostics)


def test_current_snapshot_cannot_mutate_saved_revision(default_config: Config) -> None:
    project = add_revision(new_project(default_config), Schedule(config=default_config, days=[]))
    before = serialize_project(project)
    current_schedule(project).config.seed = 99
    assert serialize_project(project) == before


def test_config_update_invalidates_selected_existing_month(default_config: Config) -> None:
    project = add_revision(new_project(default_config), Schedule(config=default_config, days=[]))
    april = default_config.model_copy(update={"month": 4})
    project = add_revision(project, Schedule(config=april, days=[]))
    project.selected_period = "2026-03"
    edited = update_config(project, april.model_copy(update={"seed": 7}))
    assert current_schedule(edited).config.seed == 7
    assert edited.revisions[-1].schedule.status == "draft"
    assert current_schedule(edited).status != "ready"


@pytest.mark.parametrize("drop_middle", [False, True])
def test_load_reconstructs_entire_active_month_dependency_chain(
    planning_config, drop_middle
) -> None:
    from duty_schedule.scheduler.multimonth import generate_multimonth
    from tests.conftest import complete_config

    calendars = [
        complete_config(planning_config.model_copy(update={"month": month})).production_calendar
        for month in (4, 5, 6)
    ]
    schedules = generate_multimonth(planning_config, 4, 2026, 6, 2026, calendars)
    assert len(schedules) == 3 and all(s.status == "ready" for s in schedules)
    project = new_project(planning_config)
    for schedule in schedules:
        project = add_revision(project, schedule)
    changed = schedules[0].model_copy(deep=True)
    name = next(name for name in changed.days[-1].workday if name.startswith("M"))
    changed.days[-1].workday.remove(name)
    changed.days[-1].morning.append(name)
    project = add_revision(project, changed)
    assert current_schedule(project).status == "ready"
    raw = json.loads(serialize_project(project))
    for revision in raw["revisions"]:
        revision["schedule"]["status"] = "ready"
        revision["schedule"]["diagnostics"] = []
    if drop_middle:
        raw["active_revisions"].pop("2026-05")
        with pytest.raises(ValueError, match="Некорректный файл"):
            load_project(json.dumps(raw))
        return
    restored = load_project(json.dumps(raw))
    for period in ("2026-05", "2026-06"):
        restored.selected_period = period
        current = current_schedule(restored)
        assert current.status == "diagnostic"
        assert any(d.code == "previous_revision_changed" for d in current.diagnostics)
        with pytest.raises(ExportBlockedError):
            ensure_exportable(current)


def test_project_rejects_cyclic_revision_parent_references(default_config) -> None:
    project = add_revision(new_project(default_config), Schedule(config=default_config, days=[]))
    project = add_revision(project, Schedule(config=default_config, days=[]))
    raw = json.loads(serialize_project(project))
    raw["revisions"][0]["parent_id"] = raw["revisions"][1]["id"]
    with pytest.raises(ValueError, match="Некорректный файл"):
        load_project(json.dumps(raw))


@pytest.mark.parametrize(
    "changelog",
    ["invalid log", {"entries": [{"employee": "М1"}]}, {"entries": "broken"}],
)
def test_invalid_saved_changelog_is_rejected_before_replacing_project(default_config, changelog):
    from duty_schedule.ui.components import import_project_into_state

    project = add_revision(new_project(default_config), Schedule(config=default_config, days=[]))
    before = serialize_project(project)
    raw = json.loads(before)
    raw["revisions"][0]["schedule"]["metadata"]["changelog"] = changelog
    state = {"project": project}
    with pytest.raises(ValueError, match="Некорректный файл"):
        import_project_into_state(state, json.dumps(raw))
    assert serialize_project(state["project"]) == before


def test_valid_saved_changelog_is_typed_and_preserved(default_config):
    from duty_schedule.scheduler.changelog import ChangeLog

    log = ChangeLog()
    log.add("balance_evening", "swapped", "М1", date(2026, 3, 2), "detail")
    schedule = Schedule(config=default_config, days=[], metadata={"changelog": log})
    restored = load_project(serialize_project(add_revision(new_project(default_config), schedule)))
    assert restored.revisions[0].schedule.metadata["changelog"] == log


@pytest.mark.parametrize("source", ["manual", "xls"])
def test_standalone_month_with_verified_external_history_is_allowed(planning_config, source):
    from duty_schedule.scheduler import generate_schedule

    for carry in planning_config.carry_over:
        carry.source = source
        carry.no_previous_shifts = False
        carry.last_shift = ShiftType.DAY_OFF
        carry.consecutive_off = 2
    schedule = generate_schedule(planning_config)
    assert schedule.status == "ready"
    project = add_revision(new_project(planning_config), schedule)
    restored = load_project(serialize_project(project))
    assert ensure_exportable(current_schedule(restored)).status == "ready"
