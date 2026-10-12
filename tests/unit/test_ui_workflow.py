from __future__ import annotations

import calendar
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import yaml

from duty_schedule.models import (
    CalendarDay,
    CarryOverState,
    City,
    Config,
    Employee,
    NormChoice,
    PinnedAssignment,
    ProductionCalendar,
    RuleApproval,
    ScheduleType,
    ShiftType,
    VacationPeriod,
)
from duty_schedule.ui.config_io import _df_to_yaml, _yaml_to_df


@pytest.fixture
def complete_config() -> Config:
    employees = [
        Employee(name=f"M{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(4)
    ] + [
        Employee(name=f"K{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(2)
    ]
    employees[0].sick_leaves = [VacationPeriod(start=date(2026, 4, 1), end=date(2026, 4, 2))]
    days = []
    for number in range(1, calendar.monthrange(2026, 4)[1] + 1):
        day = date(2026, 4, number)
        kind = "off" if day.weekday() >= 5 else "working"
        if number == 4:
            kind = "working"
        if number == 3:
            kind = "short"
        days.append(CalendarDay(date=day, kind=kind))
    snapshot = ProductionCalendar(
        year=2026,
        month=4,
        days=days,
        source="fixture",
        fetched_at=datetime(2026, 3, 25, tzinfo=UTC),
    )
    return Config(
        month=4,
        year=2026,
        timezone="Asia/Vladivostok",
        solver="cpsat",
        optimization_priority="isolated_weekends",
        employees=employees,
        production_calendar=snapshot,
        norm_choices=[NormChoice(employee_name="M0", year=2026, month=4, mode="full")],
        pins=[
            PinnedAssignment(
                date=date(2026, 4, 6), employee_name="M0", shift="workday", working_hours=4
            )
        ],
        approvals=[
            RuleApproval(
                employee_name="M0",
                date=date(2026, 4, 6),
                rule="individual_workday",
                purpose="monthly_norm",
                value=4,
            )
        ],
        carry_over=[
            CarryOverState(
                employee_name=e.name,
                employee_id=e.employee_id,
                as_of=date(2026, 3, 31),
                source="manual",
                last_shift=ShiftType.DAY_OFF,
                consecutive_off=1,
            )
            for e in employees
        ],
    )


def test_yaml_roundtrip_preserves_all_typed_fields(complete_config: Config) -> None:
    raw = yaml.safe_dump(complete_config.model_dump(mode="json"), allow_unicode=True)
    df, pins, carry, month, year, seed, dates, error, priority = _yaml_to_df(raw, 2026)
    assert error is None
    assert df is not None and pins is not None
    saved = _df_to_yaml(df, month, year, seed, dates, pins, carry, priority)
    loaded = Config.model_validate(yaml.safe_load(saved))
    assert loaded.model_dump(mode="json") == complete_config.model_dump(mode="json")


@pytest.mark.parametrize(
    "raw", ["month: xxx\nemployees: []", "employees: wrong", "employees: []", "[]"]
)
def test_yaml_import_is_atomic_for_invalid_input(complete_config: Config, raw: str) -> None:
    from duty_schedule.project import new_project
    from duty_schedule.ui.components import import_config_into_state

    original = new_project(complete_config)
    state = {"project": original, "unrelated": "preserved"}
    with pytest.raises(ValueError):
        import_config_into_state(state, raw)
    assert state["project"] is original
    assert state["unrelated"] == "preserved"


def test_rename_in_tables_preserves_employee_identity_and_absences(complete_config: Config) -> None:
    from duty_schedule.ui.config_io import config_from_tables, config_to_tables

    tables = config_to_tables(complete_config)
    tables.employees.loc[0, "Имя"] = "Новое имя"
    updated = config_from_tables(
        tables.employees, complete_config, tables.employee_dates, tables.pins
    )
    assert updated.employees[0].name == "Новое имя"
    assert updated.employees[0].employee_id == complete_config.employees[0].employee_id
    assert updated.employees[0].sick_leaves == complete_config.employees[0].sick_leaves
    assert updated.norm_choices[0].employee_name == "Новое имя"
    assert updated.carry_over[0].employee_name == "Новое имя"
    assert updated.pins[0].employee_name == "Новое имя"


def test_empty_team_is_rejected_instead_of_demo_substitution() -> None:
    result = _yaml_to_df("month: 4\nyear: 2026\nemployees: []", 2026)
    assert result[0] is None
    assert result[7]


def test_invalid_schedule_edit_does_not_remove_real_absence(complete_config: Config) -> None:
    from duty_schedule.models import DaySchedule, Schedule
    from duty_schedule.ui.builders import _edit_df_to_schedule, _schedule_to_edit_df

    day = DaySchedule(
        date=date(2026, 4, 1), sick_leave=["M0"], morning=["M1"], evening=["M2"], night=["K0"]
    )
    schedule = Schedule(config=complete_config, days=[day])
    table = _schedule_to_edit_df(schedule)
    table.loc[0, "Рабочий день"] = "M0"
    edited = _edit_df_to_schedule(table, schedule)
    assert edited.config.employees[0].is_on_sick_leave(day.date)
    assert "M0" in edited.days[0].sick_leave


def test_editor_preserves_individual_workday_hours(complete_config: Config) -> None:
    from duty_schedule.models import DaySchedule, Schedule
    from duty_schedule.ui.builders import _edit_df_to_schedule, _schedule_to_edit_df

    day = DaySchedule(date=date(2026, 4, 6), workday=["M0"], workday_hours={"M0": 4})
    schedule = Schedule(config=complete_config, days=[day])
    restored = _edit_df_to_schedule(_schedule_to_edit_df(schedule), schedule)
    assert restored.days[0].workday_hours == {"M0": 4}


def test_whatif_ui_uses_the_api_patch_fields() -> None:
    from duty_schedule.api.schemas import VariantPatch
    from duty_schedule.ui.components import WHATIF_PARAMETERS

    assert set(WHATIF_PARAMETERS) == set(Config.model_fields) - {"month", "year"}
    for parameter in WHATIF_PARAMETERS:
        VariantPatch(name="test", patch={parameter: None})
    assert "month" not in WHATIF_PARAMETERS and "year" not in WHATIF_PARAMETERS


def test_project_import_is_atomic_for_invalid_file(complete_config: Config) -> None:
    from duty_schedule.project import new_project
    from duty_schedule.ui.components import import_project_into_state

    original = new_project(complete_config)
    state = {"project": original}
    with pytest.raises(ValueError):
        import_project_into_state(state, b'{"schema_version":999}')
    assert state["project"] is original


def test_blank_dataframe_names_are_not_stringified_nan(complete_config: Config) -> None:
    from duty_schedule.ui.config_io import config_from_tables, config_to_tables

    tables = config_to_tables(complete_config)
    extra = pd.DataFrame([dict.fromkeys(tables.employees.columns)])
    updated = config_from_tables(
        pd.concat([tables.employees, extra], ignore_index=True),
        complete_config,
        tables.employee_dates,
        tables.pins,
    )
    assert len(updated.employees) == len(complete_config.employees)


def test_manual_history_requires_explicit_known_or_new_employee(complete_config: Config) -> None:
    from duty_schedule.ui.components import _carry_from_frame

    employee = complete_config.employees[0]
    frame = pd.DataFrame(
        [
            {
                "ID": employee.employee_id,
                "История известна": False,
                "Новый сотрудник": True,
                "Последний статус": "Выходной",
                "Рабочая серия": 0,
            }
        ]
    )
    result = _carry_from_frame(frame, complete_config, date(2026, 3, 31))
    assert result[0].source == "new_employee"
    assert result[0].no_previous_shifts
    frame.loc[0, "Новый сотрудник"] = False
    unknown = _carry_from_frame(frame, complete_config, date(2026, 3, 31))
    assert unknown[0].source == "legacy" and unknown[0].as_of is None


def test_individual_workday_rejects_calendar_nonworking_date() -> None:
    from duty_schedule.project import new_project, serialize_project
    from duty_schedule.ui.components import assign_individual_workday
    from tests.ui.fixtures import journey_config

    project = new_project(journey_config())
    before = serialize_project(project)
    with pytest.raises(ValueError, match="рабочую дату"):
        assign_individual_workday(project, "M0", date(2026, 4, 5), 4)
    assert serialize_project(project) == before


def test_real_streamlit_project_edit_check_and_reopen(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from duty_schedule.project import current_schedule, load_project, new_project, serialize_project
    from tests.ui.fixtures import journey_config

    def no_network(*args: object, **kwargs: object) -> None:
        pytest.fail("Saved complete calendar must be used without network")

    monkeypatch.setattr("duty_schedule.ui.components.fetch_production_calendar", no_network)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "app.py"))
    app.session_state["autosave_initialized"] = True
    app.session_state["project"] = new_project(journey_config())
    app.run(timeout=20)
    assert not app.exception
    next(button for button in app.button if button.label == "Сгенерировать расписание").click().run(
        timeout=20
    )
    assert not app.exception
    assert current_schedule(app.session_state["project"]).status == "ready"

    for number in (2, 10):
        next(widget for widget in app.date_input if widget.label == "Дата «Р»").set_value(
            date(2026, 4, number)
        )
        next(
            widget for widget in app.number_input if widget.label == "Индивидуальные рабочие часы"
        ).set_value(4)
        next(
            button for button in app.button if button.label == "Назначить «Р» и подтвердить часы"
        ).click().run(timeout=20)
        assert not app.exception
        assert current_schedule(app.session_state["project"]).status == "draft"
        next(
            button for button in app.button if button.label == "Проверить текущую версию"
        ).click().run(timeout=20)
        assert not app.exception
        assert current_schedule(app.session_state["project"]).status == (
            "diagnostic" if number == 2 else "ready"
        )

    project = app.session_state["project"]
    schedule = current_schedule(project)
    assert schedule.days[1].workday_hours["M0"] == 4
    assert schedule.days[9].workday_hours["M0"] == 4
    assert schedule.monthly_targets["M0"].selected_hours == 136
    reopened = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "app.py"))
    reopened.session_state["autosave_initialized"] = True
    reopened.session_state["project"] = load_project(serialize_project(project))
    reopened.run(timeout=20)
    assert not reopened.exception
    restored = current_schedule(reopened.session_state["project"])
    assert restored.days == schedule.days
    assert restored.metadata["carry_over"] == schedule.metadata["carry_over"]


def test_ui_range_keeps_first_ready_month_and_stops_at_diagnostic() -> None:
    from duty_schedule.project import current_schedule, new_project
    from duty_schedule.ui.components import generate_project
    from tests.ui.fixtures import journey_config

    config = journey_config()
    config.employees[0].vacations = [VacationPeriod(start=date(2026, 5, 1), end=date(2026, 5, 31))]
    may_dates = [date(2026, 5, number) for number in range(1, 32)]
    working = set([day for day in may_dates if day.weekday() < 5][:17])
    may = ProductionCalendar(
        year=2026,
        month=5,
        days=[
            CalendarDay(date=day, kind="working" if day in working else "off") for day in may_dates
        ],
        source="offline_test_fixture",
        fetched_at=datetime(2026, 3, 25, tzinfo=UTC),
    )
    project = new_project(config)
    project.calendars = [config.production_calendar, may]
    result = generate_project(project, (2026, 4), (2026, 6))
    assert sorted(result.active_revisions) == ["2026-04", "2026-05"]
    assert result.selected_period == "2026-05"
    assert current_schedule(result).status == "diagnostic"
    april_id = result.active_revisions["2026-04"]
    assert next(item.schedule for item in result.revisions if item.id == april_id).status == "ready"


def test_ui_range_preserves_configuration_and_manual_pins_of_each_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duty_schedule.models import Schedule
    from duty_schedule.project import add_revision, current_schedule, new_project
    from duty_schedule.ui.components import generate_project
    from tests.ui.fixtures import journey_config, journey_days

    def no_network(*args: object, **kwargs: object) -> None:
        pytest.fail("The range must use the saved calendars of both periods")

    monkeypatch.setattr("duty_schedule.scheduler.multimonth.fetch_production_calendar", no_network)
    config = journey_config()
    project = add_revision(new_project(config), Schedule(config=config, days=journey_days(config)))
    april = current_schedule(project)
    may = ProductionCalendar(
        year=2026,
        month=5,
        days=[
            CalendarDay(
                date=date(2026, 5, number),
                kind="working" if date(2026, 5, number).weekday() < 5 else "off",
            )
            for number in range(1, 32)
        ],
        source="offline_test_fixture",
        fetched_at=datetime(2026, 3, 25, tzinfo=UTC),
    )
    may_config = config.model_copy(deep=True)
    may_config.month = 5
    may_config.seed = 73
    may_config.production_calendar = may
    may_config.carry_over = [
        CarryOverState.model_validate(item) for item in april.metadata["carry_over"]
    ]
    may_config.pins = [
        PinnedAssignment(date=date(2026, 5, 10), employee_name="M0", shift="day_off"),
        PinnedAssignment(date=date(2026, 5, 10), employee_name="M1", shift="morning"),
    ]
    may_config.norm_choices = [NormChoice(employee_name="M0", year=2026, month=5, mode="full")]
    may_config.approvals = [
        RuleApproval(
            employee_name="M1",
            date=date(2026, 5, 10),
            rule="weekly_day_off",
            purpose="coverage",
        )
    ]
    project = add_revision(project, Schedule(config=may_config, days=[]))
    project.selected_period = "2026-04"
    project.config = april.config.model_copy(deep=True)

    result = generate_project(project, (2026, 4), (2026, 5))

    regenerated = current_schedule(result)
    assert regenerated.config.month == 5
    assert regenerated.config.seed == may_config.seed
    assert regenerated.config.pins == may_config.pins
    assert regenerated.config.norm_choices == may_config.norm_choices
    assert regenerated.config.approvals == may_config.approvals
    assert regenerated.days[9].day_off.count("M0") == 1
    assert regenerated.days[9].morning.count("M1") == 1
    april_id = result.active_revisions["2026-04"]
    assert next(item.schedule for item in result.revisions if item.id == april_id).status == "ready"


def test_whatif_calendar_mismatch_is_reported_without_crashing_application() -> None:
    import json
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from duty_schedule.models import Schedule
    from duty_schedule.project import add_revision, new_project
    from tests.ui.fixtures import journey_config, journey_days

    config = journey_config()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "app.py"))
    app.session_state["autosave_initialized"] = True
    app.session_state["project"] = add_revision(
        new_project(config), Schedule(config=config, days=journey_days(config))
    )
    app.run(timeout=20)
    assert not app.exception
    wrong_period = config.production_calendar.model_dump(mode="json")
    wrong_period["year"] = 2027
    for record in wrong_period["days"]:
        record["date"] = record["date"].replace("2026-", "2027-")
    next(widget for widget in app.text_area if widget.label == "Изменения JSON").set_value(
        json.dumps({"production_calendar": wrong_period})
    )

    next(button for button in app.button if button.label == "Симулировать").click().run(timeout=20)

    assert not app.exception
    assert any("Период производственного календаря" in item.value for item in app.error)


@pytest.mark.parametrize("old_hours, expected_hours", [(3, 3), (None, 8)])
def test_revision_comparison_displays_changed_individual_workday_hours(
    old_hours: int | None, expected_hours: int
) -> None:
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from duty_schedule.models import Schedule
    from duty_schedule.project import add_revision, apply_assignments, new_project
    from tests.ui.fixtures import journey_config, journey_days

    config = journey_config()
    original_days = journey_days(config)
    if old_hours is not None:
        original_days[1].workday_hours["M0"] = old_hours
    project = add_revision(new_project(config), Schedule(config=config, days=original_days))
    edited_days = [day.model_copy(deep=True) for day in original_days]
    edited_days[1].workday_hours["M0"] = 4
    project = apply_assignments(project, edited_days)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "app.py"))
    app.session_state["autosave_initialized"] = True
    app.session_state["project"] = project

    app.run(timeout=20)

    assert not app.exception
    comparison = next(item.value for item in app.dataframe if "Было, ч" in item.value.columns)
    changed = comparison[comparison["Сотрудник"] == "M0"].iloc[0]
    assert changed["Было, ч"] == expected_hours
    assert changed["Стало, ч"] == 4


def test_duty_only_label_and_hidden_fields_preserved(complete_config):
    from streamlit.testing.v1 import AppTest

    from duty_schedule.project import new_project

    config = complete_config.model_copy(deep=True)
    config.employees[0].morning_only = True
    config.employees[0].always_on_duty = True
    app = AppTest.from_file(
        str(__import__("pathlib").Path(__file__).resolve().parents[2] / "app.py")
    )
    app.session_state["project"] = new_project(config)
    app.session_state["autosave_initialized"] = True
    app.run()
    assert not app.exception
    import json

    editor = next(e for e in app.dataframe if "Всегда на деж." in json.loads(e.proto.columns))

    columns = json.loads(editor.proto.columns)
    assert columns["Всегда на деж."]["label"] == "Только дежурства"
    assert list(editor.proto.column_order) == ["Имя", "Город", "График", "Дежурный"]
    next(b for b in app.button if b.label == "Сохранить настройки").click().run()
    assert not app.exception
    employee = app.session_state["project"].config.employees[0]
    assert employee.always_on_duty and employee.morning_only
    assert employee.employee_id == config.employees[0].employee_id
