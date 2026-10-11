from __future__ import annotations

import contextlib
import hashlib
import tempfile
import warnings
from collections.abc import MutableMapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from duty_schedule.calendar import CalendarError, fetch_production_calendar
from duty_schedule.models import (
    SHIFT_NAMES_RU,
    CarryOverState,
    City,
    Config,
    DaySchedule,
    Employee,
    NormChoice,
    PinnedAssignment,
    ProductionCalendar,
    RuleApproval,
    Schedule,
    ScheduleDiagnostic,
    ScheduleType,
    ShiftType,
    VacationPeriod,
)
from duty_schedule.project import (
    ExportBlockedError,
    ScheduleProject,
    add_revision,
    apply_assignments,
    check_current,
    current_schedule,
    ensure_exportable,
    load_project,
    new_project,
    remove_pin,
    serialize_project,
    update_config,
)
from duty_schedule.scheduler import ScheduleError, generate_schedule
from duty_schedule.stats import build_assignments, compute_stats
from duty_schedule.ui.builders import _edit_df_to_schedule, _schedule_to_edit_df
from duty_schedule.ui.config_io import (
    _pins_df_to_list,
    config_from_tables,
    config_to_tables,
    dump_config_yaml,
    parse_config_yaml,
)
from duty_schedule.ui.mappings import (
    _DEFAULT_ROWS,
    _SHIFTS_RU,
    _WEEKDAY_OPTIONS,
    MONTHS_RU,
)
from duty_schedule.workload import calculate_monthly_targets

WHATIF_PARAMETERS = tuple(field for field in Config.model_fields if field not in {"month", "year"})


def _default_config() -> Config:
    from duty_schedule.ui.config_io import employees_from_table

    today = date.today()
    month = today.month % 12 + 1
    year = today.year + (today.month == 12)
    return Config(
        month=month, year=year, employees=employees_from_table(pd.DataFrame(_DEFAULT_ROWS))
    )


def _set_project(state: MutableMapping[Any, Any], project: ScheduleProject) -> None:
    state["project"] = project
    state["ui_epoch"] = int(state.get("ui_epoch", 0)) + 1
    state.pop("ui_exports", None)
    state.pop("ui_import_notice", None)


def import_config_into_state(state: MutableMapping[Any, Any], content: str) -> Config:
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always", UserWarning)
        config = parse_config_yaml(content)
    state["ui_migration_notices"] = [str(notice.message) for notice in notices]
    previous = state.get("project")
    project = (
        update_config(previous, config)
        if isinstance(previous, ScheduleProject)
        else new_project(config)
    )
    _set_project(state, project)
    return config


def import_project_into_state(
    state: MutableMapping[Any, Any], content: bytes | str
) -> ScheduleProject:
    project = load_project(content)
    _set_project(state, project)
    return project


def _saved_calendar(project: ScheduleProject, year: int, month: int) -> ProductionCalendar | None:
    config_calendar = project.config.production_calendar
    records = list(project.calendars)
    if config_calendar is not None:
        records.append(config_calendar)
    return next(
        (
            record
            for record in reversed(records)
            if (record.year, record.month) == (year, month) and record.verified
        ),
        None,
    )


def _config_for_period(project: ScheduleProject, year: int, month: int) -> Config:
    period = f"{year:04d}-{month:02d}"
    revision_id = project.active_revisions.get(period)
    revision = next((item for item in project.revisions if item.id == revision_id), None)
    source = project.config
    if (source.year, source.month) != (year, month) and revision is not None:
        source = revision.schedule.config
    config = source.model_copy(deep=True)
    config.year, config.month = year, month
    config.production_calendar = _saved_calendar(project, year, month)
    previous_year, previous_month = (year - 1, 12) if month == 1 else (year, month - 1)
    previous_id = project.active_revisions.get(f"{previous_year:04d}-{previous_month:02d}")
    previous = next(
        (revision.schedule for revision in project.revisions if revision.id == previous_id), None
    )
    if previous is not None and previous.status == "ready":
        checked = ensure_exportable(previous)
        config._quality_state = "available"
        config._quality_origin = "project"
        config.previous_schedule = checked.model_copy(deep=True)
        config.previous_schedule.config.previous_schedule = None
        config.carry_over = [
            CarryOverState.model_validate(item) for item in checked.metadata.get("carry_over", [])
        ]
    else:
        config.previous_schedule = None
    return config


def _generate_range_project(
    project: ScheduleProject, start: tuple[int, int], end: tuple[int, int], rebuild: bool = False
) -> ScheduleProject:
    date(*start, 1)
    date(*end, 1)
    if end < start:
        raise ValueError("Конец диапазона должен быть не раньше начала")
    result = project
    year, month = start
    while (year, month) <= end:
        config = _config_for_period(result, year, month)
        target = result.model_copy(deep=True)
        target.config = config
        target.selected_period = f"{year:04d}-{month:02d}"
        result = generate_project(target, rebuild=rebuild)
        if result.repair_candidate is not None:
            break
        active = current_schedule(result)
        if active is None or active.status != "ready":
            break
        month = month % 12 + 1
        year += month == 1
    return result


def generate_project(
    project: ScheduleProject,
    start: tuple[int, int] | None = None,
    end: tuple[int, int] | None = None,
    rebuild: bool = False,
) -> ScheduleProject:
    if start is not None and end is not None:
        return _generate_range_project(project, start, end, rebuild)
    config = _config_for_period(project, project.config.year, project.config.month)
    if config.production_calendar is None:
        with contextlib.suppress(CalendarError):
            config.production_calendar = fetch_production_calendar(config.year, config.month)
    try:
        schedule = generate_schedule(
            config, baseline=None if rebuild else current_schedule(project)
        )
    except ScheduleError as exc:
        schedule = Schedule(
            config=config,
            days=[],
            status="diagnostic",
            diagnostics=[ScheduleDiagnostic(code="generation_failed", detail=str(exc))],
        )
    if current_schedule(project) is not None and schedule.status != "ready" and not rebuild:
        return project.model_copy(update={"repair_candidate": schedule}, deep=True)
    result = add_revision(project, schedule)
    result.repair_candidate = None
    return result


def _commit(config: Config) -> None:
    _set_project(st.session_state, update_config(st.session_state["project"], config))
    st.rerun()


def _key(label: str) -> str:
    return f"ui_{st.session_state.get('ui_epoch', 0)}_{label}"


def _sidebar(project: ScheduleProject) -> None:
    with st.sidebar:
        st.header("Рабочий проект")
        for label, file_types in (
            ("Открыть рабочий проект (.json)", ["json"]),
            ("Загрузить конфиг (.yaml)", ["yaml", "yml"]),
        ):
            uploaded = st.file_uploader(label, type=file_types, key=_key(label))
            if uploaded is not None:
                content = uploaded.getvalue()
                digest = hashlib.sha256(content).hexdigest()
                token = (uploaded.file_id, digest)
                if st.session_state.get(f"loaded_{label}") != token:
                    try:
                        if file_types[0] == "yaml":
                            import_config_into_state(st.session_state, content.decode("utf-8"))
                        else:
                            import_project_into_state(st.session_state, content)
                    except (ValueError, UnicodeDecodeError) as exc:
                        st.error(str(exc))
                    else:
                        st.session_state[f"loaded_{label}"] = token
                        st.session_state["ui_import_notice"] = f"Загружено: {uploaded.name}"
                        st.rerun()
        for notice in st.session_state.get("ui_migration_notices", []):
            st.warning(notice)
        if st.session_state.get("ui_import_notice"):
            st.text(st.session_state["ui_import_notice"])
        st.download_button(
            "Сохранить рабочий проект",
            serialize_project(project),
            file_name="schedule-project.json",
            mime="application/json",
            key=_key("save_project"),
            use_container_width=True,
        )
        st.download_button(
            "Скачать конфиг (.yaml)",
            dump_config_yaml(project.config),
            file_name=f"config_{project.config.year}_{project.config.month:02d}.yaml",
            mime="text/yaml",
            key=_key("save_config"),
            use_container_width=True,
        )
        st.caption(
            "Проект сохраняет календарь, версии, ручные назначения, подтверждения и историю."
        )
        periods = sorted(set(project.active_revisions) | {project.selected_period})
        if periods:
            selected = st.selectbox(
                "Текущий месяц проекта",
                periods,
                index=periods.index(project.selected_period)
                if project.selected_period in periods
                else 0,
                key=_key("selected_period"),
            )
            if selected != project.selected_period:
                changed = project.model_copy(deep=True)
                changed.selected_period = selected
                schedule = current_schedule(changed)
                if schedule is not None:
                    changed.config = schedule.config.model_copy(deep=True)
                _set_project(st.session_state, changed)
                st.rerun()


def _basic_configuration(project: ScheduleProject) -> None:
    config = project.config
    tables = config_to_tables(config)
    with st.form(_key("configuration_form")):
        c1, c2, c3 = st.columns(3)
        month = c1.selectbox(
            "Месяц",
            range(1, 13),
            index=config.month - 1,
            format_func=lambda value: MONTHS_RU[value - 1],
        )
        year = c2.number_input("Год", min_value=2024, value=config.year, step=1)
        with st.expander("Дополнительные настройки"):
            seed = st.number_input("Seed", min_value=0, value=config.seed, step=1)
            solver = st.selectbox(
                "Алгоритм", ["greedy", "cpsat"], index=int(config.solver == "cpsat")
            )
        timezone_name = config.timezone
        employees = st.data_editor(
            tables.employees,
            column_config={
                "ID": None,
                "Город": st.column_config.SelectboxColumn(options=["Москва", "Хабаровск"]),
                "График": st.column_config.SelectboxColumn(options=["Гибкий", "5/2"]),
                "Предпочт. смена": st.column_config.SelectboxColumn(
                    options=["", "Утро", "Вечер", "Ночь", "Рабочий день"]
                ),
                "Макс. подряд": st.column_config.NumberColumn(
                    min_value=1,
                    max_value=7,
                    step=1,
                    help=(
                        "Обычный предел 6; превышение персонального лимита подтверждается отдельно"
                    ),
                ),
            },
            disabled=["ID"],
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key=_key("employees_table"),
        )
        if st.form_submit_button("Сохранить настройки"):
            try:
                updated = config_from_tables(employees, config, tables.employee_dates)
                updated = Config.model_validate(
                    {
                        **updated.model_dump(),
                        "month": month,
                        "year": year,
                        "seed": seed,
                        "solver": solver,
                        "timezone": timezone_name,
                        "production_calendar": _saved_calendar(project, year, month),
                    }
                )
                if updated.production_calendar is not None and (
                    updated.production_calendar.year,
                    updated.production_calendar.month,
                ) != (year, month):
                    updated.production_calendar = _saved_calendar(project, year, month)
            except ValueError as exc:
                st.error(str(exc))
            else:
                _commit(updated)
    st.caption(
        "Дежурства: утро 08–17 МСК, вечер 15–00 МСК, ночь 00–08 МСК одной даты. "
        "«Р» начинается в 09:00 местного времени."
    )


def _period_frame(periods: list[VacationPeriod]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Начало": period.start, "Конец": period.end} for period in periods],
        columns=["Начало", "Конец"],
    )


def _employee_tools(project: ScheduleProject) -> None:
    config = project.config
    sort_by = st.selectbox(
        "Сортировать сотрудников", ["По умолчанию", "Имя", "Город", "График", "Дежурный"]
    )
    descending = st.checkbox("По убыванию", value=False)
    if st.button("Сортировать"):
        fields = {"Имя": "name", "Город": "city", "График": "schedule_type", "Дежурный": "on_duty"}
        if sort_by == "По умолчанию":
            employees = sorted(
                config.employees,
                key=lambda item: (
                    item.city != City.MOSCOW,
                    item.on_duty,
                    item.schedule_type != ScheduleType.FIVE_TWO,
                    item.name,
                ),
                reverse=descending,
            )
        else:
            employees = sorted(
                config.employees,
                key=lambda item: getattr(item, fields[sort_by]),
                reverse=descending,
            )
        _commit(config.model_copy(update={"employees": employees}, deep=True))
    presets = st.columns(3)
    for column, label, city, on_duty, schedule_type in (
        (presets[0], "+ Москва, дежурный", City.MOSCOW, True, ScheduleType.FLEXIBLE),
        (presets[1], "+ Хабаровск, ночной", City.KHABAROVSK, True, ScheduleType.FLEXIBLE),
        (presets[2], "+ Не дежурит (5/2)", City.MOSCOW, False, ScheduleType.FIVE_TWO),
    ):
        if column.button(label, use_container_width=True):
            number = 1
            while f"Новый сотрудник {number}" in {item.name for item in config.employees}:
                number += 1
            employee = Employee(
                name=f"Новый сотрудник {number}",
                city=city,
                schedule_type=schedule_type,
                on_duty=on_duty,
            )
            _commit(
                config.model_copy(update={"employees": [*config.employees, employee]}, deep=True)
            )
    with st.expander("Массовое редактирование"):
        selected = st.multiselect(
            "Сотрудники",
            [employee.name for employee in config.employees],
            key=_key("bulk_employees"),
        )
        fields = {
            "Город": "city",
            "График": "schedule_type",
            "Дежурный": "on_duty",
            "Всегда на деж.": "always_on_duty",
            "Только утро": "morning_only",
            "Только вечер": "evening_only",
            "Предпочт. смена": "preferred_shift",
            "Макс. подряд": "max_consecutive_working",
        }
        field = st.selectbox("Столбец", list(fields), key=_key("bulk_field"))
        value: Any
        if field == "Город":
            value = st.selectbox(
                "Значение",
                list(City),
                format_func=lambda city: "Москва" if city == City.MOSCOW else "Хабаровск",
            )
        elif field == "График":
            value = st.selectbox(
                "Значение",
                list(ScheduleType),
                format_func=lambda item: "Гибкий" if item == ScheduleType.FLEXIBLE else "5/2",
            )
        elif field == "Макс. подряд":
            value = st.number_input("Значение", min_value=1, max_value=7, value=6, step=1)
        elif field == "Предпочт. смена":
            value = st.selectbox(
                "Значение",
                [None, ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT, ShiftType.WORKDAY],
                format_func=lambda item: SHIFT_NAMES_RU[item] if item else "Без предпочтения",
            )
        else:
            value = st.checkbox("Значение")
        if st.button("Применить массовые изменения", disabled=not selected):
            data = config.model_dump()
            for employee_data in data["employees"]:
                if employee_data["name"] in selected:
                    employee_data[fields[field]] = value
            try:
                changed = Config.model_validate(data)
            except ValueError as exc:
                st.error(str(exc))
            else:
                _commit(changed)


def _read_periods(frame: pd.DataFrame) -> list[VacationPeriod]:
    result = []
    for _, row in frame.iterrows():
        if pd.isna(row["Начало"]) and pd.isna(row["Конец"]):
            continue
        result.append(VacationPeriod(start=row["Начало"], end=row["Конец"]))
    return result


def _employee_constraints(project: ScheduleProject) -> None:
    config = project.config
    employee = st.selectbox(
        "Сотрудник",
        config.employees,
        format_func=lambda item: item.name,
        key=_key("constraint_employee"),
    )
    selected_mode = next(
        (
            choice.mode
            for choice in config.norm_choices
            if choice.employee_name == employee.name
            and (choice.year, choice.month) == (config.year, config.month)
        ),
        "adjusted",
    )
    snapshot = _saved_calendar(project, config.year, config.month)
    if snapshot is not None:
        target = calculate_monthly_targets(config, snapshot)[employee.name]
        c1, c2, c3 = st.columns(3)
        c1.metric("Календарная норма, ч", target.calendar_hours)
        c2.metric("После отсутствий, ч", target.adjusted_hours)
        c3.metric("Выбранная цель, ч", target.selected_hours)
    with st.form(_key(f"constraints_{employee.employee_id}")):
        st.markdown("**Отпуск**")
        vacations = st.data_editor(
            _period_frame(employee.vacations),
            column_config={
                "Начало": st.column_config.DateColumn(),
                "Конец": st.column_config.DateColumn(),
            },
            num_rows="dynamic",
            hide_index=True,
            key=_key("vacations"),
        )
        st.markdown("**Больничный**")
        sick_leaves = st.data_editor(
            _period_frame(employee.sick_leaves),
            column_config={
                "Начало": st.column_config.DateColumn(),
                "Конец": st.column_config.DateColumn(),
            },
            num_rows="dynamic",
            hide_index=True,
            key=_key("sick_leaves"),
        )
        blocked = st.data_editor(
            pd.DataFrame({"Дата": employee.unavailable_dates}, dtype=object),
            column_config={"Дата": st.column_config.DateColumn()},
            num_rows="dynamic",
            hide_index=True,
            key=_key("unavailable"),
        )
        weekly = st.multiselect(
            "Фиксированные выходные",
            _WEEKDAY_OPTIONS,
            default=[_WEEKDAY_OPTIONS[number] for number in employee.days_off_weekly],
        )
        mode = st.radio(
            "Цель месяца",
            ["adjusted", "full"],
            index=int(selected_mode == "full"),
            format_func=lambda value: (
                "Норма после отпуска и больничного"
                if value == "adjusted"
                else "Полная календарная норма"
            ),
        )
        if st.form_submit_button("Сохранить ограничения и цель"):
            try:
                updated = config.model_copy(deep=True)
                item = next(
                    item for item in updated.employees if item.employee_id == employee.employee_id
                )
                item.vacations = _read_periods(vacations)
                item.sick_leaves = _read_periods(sick_leaves)
                item.unavailable_dates = [
                    pd.Timestamp(day).date() for day in blocked["Дата"] if not pd.isna(day)
                ]
                item.days_off_weekly = [_WEEKDAY_OPTIONS.index(label) for label in weekly]
                updated.norm_choices = [
                    choice
                    for choice in updated.norm_choices
                    if not (
                        choice.employee_id == employee.employee_id
                        or choice.employee_name == employee.name
                    )
                    or (choice.year, choice.month) != (config.year, config.month)
                ]
                updated.norm_choices.append(
                    NormChoice.model_validate(
                        {
                            "employee_name": employee.name,
                            "employee_id": employee.employee_id,
                            "year": config.year,
                            "month": config.month,
                            "mode": mode,
                        }
                    )
                )
                updated = Config.model_validate(updated.model_dump())
            except ValueError as exc:
                st.error(str(exc))
            else:
                _commit(updated)


def _carry_from_frame(frame: pd.DataFrame, config: Config, as_of: date) -> list[CarryOverState]:
    result = []
    by_id = {employee.employee_id: employee for employee in config.employees}
    labels = {label: shift for shift, label in SHIFT_NAMES_RU.items()}
    for _, row in frame.iterrows():
        employee = by_id[str(row["ID"])]
        previous = next(
            (
                item
                for item in config.carry_over
                if item.employee_id == employee.employee_id or item.employee_name == employee.name
            ),
            None,
        )
        if previous is not None and (
            bool(row["Новый сотрудник"]) == previous.no_previous_shifts
            and bool(row["История известна"])
            == (previous.as_of == as_of and previous.source != "legacy")
            and row["Последний статус"] == SHIFT_NAMES_RU[previous.last_shift or ShiftType.DAY_OFF]
            and int(row["Рабочая серия"]) == previous.consecutive_working
            and all(
                column not in row or int(row[column]) == getattr(previous, field)
                for column, field in (
                    ("Серия отдыха", "consecutive_off"),
                    ("Серия одной смены", "consecutive_same_shift"),
                )
            )
        ):
            result.append(previous.model_copy(deep=True))
            continue
        if row["Новый сотрудник"]:
            result.append(
                CarryOverState(
                    employee_name=employee.name,
                    employee_id=employee.employee_id,
                    source="new_employee",
                    as_of=as_of,
                    no_previous_shifts=True,
                )
            )
        elif row["История известна"]:
            shift = labels[row["Последний статус"]]
            working = shift in (
                ShiftType.MORNING,
                ShiftType.EVENING,
                ShiftType.NIGHT,
                ShiftType.WORKDAY,
            )
            count = int(row["Рабочая серия"])
            if working and count < 1:
                raise ValueError(
                    f"{employee.name}: для рабочего последнего дня укажите длину серии"
                )
            if "Серия отдыха" not in row or "Серия одной смены" not in row:
                raise ValueError(f"{employee.name}: уточните счётчики отдыха и одной смены")
            result.append(
                CarryOverState(
                    employee_name=employee.name,
                    employee_id=employee.employee_id,
                    last_shift=shift,
                    consecutive_working=count if working else 0,
                    consecutive_off=int(row["Серия отдыха"]),
                    consecutive_same_shift=int(row["Серия одной смены"]),
                    source="manual",
                    as_of=as_of,
                )
            )
        else:
            previous = next(
                (
                    item
                    for item in config.carry_over
                    if item.employee_id == employee.employee_id
                    or item.employee_name == employee.name
                ),
                None,
            )
            if previous is not None:
                result.append(previous.model_copy(update={"source": "legacy", "as_of": None}))
    return result


def _history_configuration(project: ScheduleProject) -> None:
    config = project.config
    previous_date = date(config.year, config.month, 1) - timedelta(days=1)
    st.caption(f"Состояние на {previous_date:%d.%m.%Y}. Неизвестная история не считается нулевой.")
    xls = st.file_uploader(
        "Загрузить предыдущий график (.xlsx)", type=["xlsx"], key=_key("history_xls")
    )
    if xls is not None and st.button("Применить историю из XLS"):
        from duty_schedule.xls_import import XlsImportError, parse_carry_over_from_xls

        try:
            imported_carry = parse_carry_over_from_xls(xls.getvalue())
            updated = config.model_copy(update={"carry_over": imported_carry}, deep=True)
        except (ValueError, XlsImportError) as exc:
            st.error(str(exc))
        else:
            _commit(updated)
    rows = []
    for employee in config.employees:
        carry = next(
            (
                item
                for item in config.carry_over
                if item.employee_id == employee.employee_id or item.employee_name == employee.name
            ),
            None,
        )
        rows.append(
            {
                "ID": employee.employee_id,
                "Сотрудник": employee.name,
                "История известна": bool(
                    carry and carry.as_of == previous_date and carry.source != "legacy"
                ),
                "Новый сотрудник": bool(carry and carry.no_previous_shifts),
                "Последний статус": SHIFT_NAMES_RU.get(
                    (carry.last_shift or ShiftType.DAY_OFF) if carry else ShiftType.DAY_OFF,
                    "Выходной",
                ),
                "Рабочая серия": carry.consecutive_working if carry else 0,
                "Серия отдыха": carry.consecutive_off if carry else 0,
                "Серия одной смены": carry.consecutive_same_shift if carry else 0,
            }
        )
    with st.form(_key("carry_form")):
        frame = st.data_editor(
            pd.DataFrame(rows),
            column_config={
                "ID": None,
                "Последний статус": st.column_config.SelectboxColumn(
                    options=list(SHIFT_NAMES_RU.values())
                ),
                "Рабочая серия": st.column_config.NumberColumn(min_value=0, step=1),
            },
            disabled=["ID", "Сотрудник"],
            hide_index=True,
            use_container_width=True,
            key=_key("carry_table"),
        )
        if st.form_submit_button("Сохранить исходную историю"):
            try:
                updated = config.model_copy(
                    update={"carry_over": _carry_from_frame(frame, config, previous_date)},
                    deep=True,
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                _commit(updated)


def _pins_configuration(project: ScheduleProject) -> None:
    config = project.config
    with st.form(_key("pins_form")):
        frame = st.data_editor(
            config_to_tables(config).pins,
            column_config={
                "Дата": st.column_config.DateColumn(format="DD.MM.YYYY"),
                "Сотрудник": st.column_config.SelectboxColumn(
                    options=[employee.name for employee in config.employees]
                ),
                "Смена": st.column_config.SelectboxColumn(options=_SHIFTS_RU),
                "Часы «Р»": st.column_config.NumberColumn(min_value=1, max_value=8, step=1),
            },
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key=_key("pins_table"),
        )
        if st.form_submit_button("Сохранить закрепления"):
            try:
                pins = [
                    PinnedAssignment.model_validate(item)
                    for item in _pins_df_to_list(frame, config.year)
                ]
                updated = config.model_copy(update={"pins": pins}, deep=True)
            except ValueError as exc:
                st.error(str(exc))
            else:
                _commit(updated)
    if config.pins:
        selected = st.multiselect(
            "Снять закрепления",
            range(len(config.pins)),
            format_func=lambda index: (
                f"{config.pins[index].date:%d.%m.%Y} · "
                f"{config.pins[index].employee_name} · "
                f"{SHIFT_NAMES_RU[config.pins[index].shift]}"
            ),
        )
        if st.button("Снять выбранные закрепления", disabled=not selected):
            changed = project
            for index in selected:
                pin = config.pins[index]
                changed = remove_pin(changed, pin.date, pin.employee_name)
            _set_project(st.session_state, changed)
            st.rerun()


def _approval_configuration(project: ScheduleProject) -> None:
    config = project.config
    labels = {
        "working_streak": "Превышение рабочей серии",
        "weekly_day_off": "Работа в фиксированный выходной",
        "individual_workday": "Индивидуальные часы «Р»",
    }
    rule = st.selectbox(
        "Исключение", list(labels), format_func=lambda item: labels[item], key=_key("approval_rule")
    )
    with st.form(_key("approval_form")):
        employee = st.selectbox(
            "Для сотрудника", config.employees, format_func=lambda item: item.name
        )
        day = st.date_input("Дата исключения", value=date(config.year, config.month, 1))
        purpose = st.radio(
            "Цель исключения",
            ["coverage", "monthly_norm"],
            format_func=lambda item: (
                "Покрытие смен" if item == "coverage" else "Выполнение выбранной нормы"
            ),
        )
        value = (
            st.number_input(
                "Разрешённая длина серии" if rule == "working_streak" else "Рабочие часы «Р»",
                min_value=1,
                max_value=7 if rule == "working_streak" else 8,
                value=7 if rule == "working_streak" else 4,
                step=1,
            )
            if rule != "weekly_day_off"
            else None
        )
        if st.form_submit_button("Подтвердить исключение"):
            approval = RuleApproval.model_validate(
                {
                    "employee_name": employee.name,
                    "employee_id": employee.employee_id,
                    "date": day,
                    "rule": rule,
                    "purpose": purpose,
                    "value": value,
                }
            )
            updated = config.model_copy(deep=True)
            updated.approvals = [
                item
                for item in updated.approvals
                if (item.employee_name, item.date, item.rule) != (employee.name, day, rule)
            ] + [approval]
            _commit(updated)
    if config.approvals:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Сотрудник": item.employee_name,
                        "Дата": item.date,
                        "Исключение": labels[item.rule],
                        "Значение": item.value,
                        "Подтверждено": item.confirmed_at,
                    }
                    for item in config.approvals
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        selected = st.multiselect(
            "Отозвать подтверждения",
            range(len(config.approvals)),
            format_func=lambda index: (
                f"{config.approvals[index].employee_name} · "
                f"{config.approvals[index].date:%d.%m} · "
                f"{labels[config.approvals[index].rule]}"
            ),
        )
        if st.button("Отозвать выбранные подтверждения", disabled=not selected):
            _commit(
                config.model_copy(
                    update={
                        "approvals": [
                            item
                            for index, item in enumerate(config.approvals)
                            if index not in selected
                        ]
                    },
                    deep=True,
                )
            )


def assign_individual_workday(
    project: ScheduleProject, employee_name: str, day: date, hours: int
) -> ScheduleProject:
    config = project.config.model_copy(deep=True)
    snapshot = _saved_calendar(project, day.year, day.month)
    if snapshot is None or not snapshot.is_working(day):
        raise ValueError(
            "«Р» допускается только в рабочую дату сохранённого производственного календаря"
        )
    if not 1 <= hours <= snapshot.hours(day):
        raise ValueError("Индивидуальные часы должны быть от 1 до нормы часов этой даты")
    employee = next(item for item in config.employees if item.name == employee_name)
    config.approvals = [
        item
        for item in config.approvals
        if (item.employee_name, item.date, item.rule) != (employee_name, day, "individual_workday")
    ]
    config.approvals.append(
        RuleApproval(
            employee_name=employee_name,
            employee_id=employee.employee_id,
            date=day,
            rule="individual_workday",
            purpose="monthly_norm",
            value=hours,
        )
    )
    config.pins = [
        pin for pin in config.pins if (pin.employee_name, pin.date) != (employee_name, day)
    ] + [
        PinnedAssignment(
            employee_name=employee_name, date=day, shift=ShiftType.WORKDAY, working_hours=hours
        )
    ]
    changed = update_config(project, config)
    schedule = current_schedule(changed)
    if schedule is not None:
        days = [item.model_copy(deep=True) for item in schedule.days]
        record = next((item for item in days if item.date == day), None)
        if record is not None:
            for shift in (
                ShiftType.MORNING,
                ShiftType.EVENING,
                ShiftType.NIGHT,
                ShiftType.WORKDAY,
                ShiftType.DAY_OFF,
            ):
                setattr(
                    record,
                    shift.value,
                    [name for name in getattr(record, shift.value) if name != employee_name],
                )
            record.workday.append(employee_name)
            record.workday_hours[employee_name] = hours
            changed = apply_assignments(changed, days)
    return changed


def _individual_workday(project: ScheduleProject) -> None:
    st.caption("Начало в 09:00 местного времени; сотрудник выбирает перерывы самостоятельно.")
    with st.form(_key("individual_workday_form")):
        employee = st.selectbox(
            "Сотрудник для «Р»", project.config.employees, format_func=lambda item: item.name
        )
        day = st.date_input("Дата «Р»", value=date(project.config.year, project.config.month, 1))
        hours = st.number_input(
            "Индивидуальные рабочие часы", min_value=1, max_value=8, value=4, step=1
        )
        if st.form_submit_button("Назначить «Р» и подтвердить часы"):
            try:
                changed = assign_individual_workday(project, employee.name, day, hours)
            except ValueError as exc:
                st.error(str(exc))
            else:
                _set_project(st.session_state, changed)
                st.rerun()


def _calendar_configuration(project: ScheduleProject) -> None:
    snapshot = _saved_calendar(project, project.config.year, project.config.month)
    if snapshot is not None:
        st.caption(
            f"Календарь {snapshot.month:02d}.{snapshot.year}: {snapshot.source}; "
            f"загружен {snapshot.fetched_at:%d.%m.%Y %H:%M}."
            + (" Используется сохранённый снимок." if snapshot.used_saved else "")
        )
    else:
        st.info("Для готового графика нужен полный производственный календарь выбранного месяца.")
    if st.button("Обновить производственный календарь"):
        try:
            loaded = fetch_production_calendar(
                project.config.year, project.config.month, saved=snapshot
            )
        except CalendarError as exc:
            st.error(str(exc))
        else:
            config = project.config.model_copy(update={"production_calendar": loaded}, deep=True)
            _commit(config)


def preparation_issues(config: Config) -> list[ScheduleDiagnostic]:
    from duty_schedule.calendar import calendar_for_config, get_all_days
    from duty_schedule.models import collect_config_issues
    from duty_schedule.scheduler.rules import can_assign_work
    from duty_schedule.scheduler.validation import validate_schedule_result

    days = []
    pins = {(pin.date, pin.employee_name): pin for pin in config.pins}
    for day in get_all_days(config.year, config.month):
        record = DaySchedule(date=day)
        for employee in config.employees:
            shift = (
                ShiftType.SICK_LEAVE
                if employee.is_on_sick_leave(day)
                else ShiftType.VACATION
                if employee.is_on_vacation(day)
                else ShiftType.DAY_OFF
            )
            pin = pins.get((day, employee.name))
            if pin:
                shift = pin.shift
                if pin.working_hours is not None:
                    record.workday_hours[employee.name] = pin.working_hours
            getattr(record, shift.value).append(employee.name)
        days.append(record)
    checked = validate_schedule_result(Schedule(config=config, days=days))
    input_codes = {
        "calendar_invalid",
        "calendar_unverified",
        "duplicate_employee",
        "duplicate_employee_id",
        "norm_choice_invalid",
        "norm_employee_unknown",
    }
    excluded = {"coverage", "monthly_hours", "assignment_missing"}
    issues = [
        item
        for item in checked.diagnostics
        if item.code.startswith("history_")
        or item.code.startswith("pin_")
        or item.code in input_codes
        or (item.code not in excluded and (item.date, item.employee_name) in pins)
    ]
    input_errors, _ = collect_config_issues(config)
    issues.extend(
        ScheduleDiagnostic(
            code="pin_configuration" if detail.startswith("Пин ") else "config_invalid",
            detail=detail,
        )
        for detail in input_errors
    )
    calendar = calendar_for_config(config)
    for day in get_all_days(config.year, config.month):
        pools = [
            [
                employee.name
                for employee in config.employees
                if can_assign_work(config, calendar, employee, day, shift, None, 0, False)
                and ((pin := pins.get((day, employee.name))) is None or pin.shift == shift)
            ]
            for shift in (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT)
        ]
        if not any(
            a != b and a != c and b != c for a in pools[0] for b in pools[1] for c in pools[2]
        ):
            issues.append(
                ScheduleDiagnostic(
                    code="staffing_unavailable",
                    date=day,
                    detail="Недостаточно подходящих сотрудников для трёх дежурств; "
                    "проверьте отсутствия и закрепления",
                )
            )
    return issues


def _preparation(project: ScheduleProject) -> list[ScheduleDiagnostic]:
    issues = preparation_issues(project.config)
    st.subheader("Готовность к расчёту")
    if project.config.optimization_priority is not None:
        st.warning("optimization_priority устарел и не меняет фиксированный порядок качества")
    groups = [
        (
            "Состав и доступность",
            {
                "staffing_unavailable",
                "duplicate_employee",
                "duplicate_employee_id",
                "config_invalid",
            },
            "2. Ограничения",
        ),
        ("Полный календарь", {"calendar_invalid", "calendar_unverified"}, "2. Ограничения"),
        (
            "История отдыха",
            {item.code for item in issues if item.code.startswith("history_")},
            "3. История",
        ),
        (
            "Закрепления",
            {item.code for item in issues if item.code.startswith("pin_") or item.approval_rule},
            "4. Закрепления",
        ),
        ("Нормы часов", {"norm_choice_invalid", "norm_employee_unknown"}, "2. Ограничения"),
    ]
    for label, codes, action in groups:
        problems = [item for item in issues if item.code in codes]
        st.write(f"{label}: {'требует исправления' if problems else 'подготовлено'}")
        actions = {
            "1. Состав"
            if item.code in {"duplicate_employee", "duplicate_employee_id", "config_invalid"}
            else action
            for item in problems
        }
        for target in sorted(actions):
            if st.button(f"Открыть «{target}»", key=f"preflight_{label}_{target}"):
                st.session_state["configuration_tabs"] = target
                st.rerun()
        for item in problems[:3]:
            st.warning(
                f"{item.employee_name or ''} {item.date or ''}: {item.detail}. Откройте «{action}»."
            )
    if issues:
        with st.expander("Все причины подготовки"):
            st.dataframe(pd.DataFrame([item.model_dump() for item in issues]), hide_index=True)
    st.caption(
        "Правки форм применяются кнопкой сохранения. "
        "Неприменённые правки не входят в сохранённую версию."
    )
    return issues


def _planning(project: ScheduleProject) -> None:
    issues = _preparation(project)
    diagnostic = st.checkbox("Диагностическое исследование неполных данных")
    rebuild = st.checkbox("Полный пересчёт без сохранения назначений")
    if project.repair_candidate is not None:
        st.warning("Пересчёт не дал готового результата. Исходная версия остаётся текущей.")
        _diagnostics(project.repair_candidate)
        if st.button("Применить диагностический черновик"):
            _set_project(st.session_state, add_revision(project, project.repair_candidate))
            st.rerun()
    multi = st.toggle("Мультимесячное планирование", key=_key("multi_mode"))
    start = end = None
    if multi:
        first = date(project.config.year, project.config.month, 1)
        start_day = st.date_input("Начало диапазона", value=first, key=_key("range_start"))
        end_day = st.date_input("Конец диапазона", value=first, key=_key("range_end"))
        start, end = (start_day.year, start_day.month), (end_day.year, end_day.month)
    if st.button(
        "Сгенерировать расписание",
        type="primary",
        use_container_width=True,
        disabled=bool(issues) and not diagnostic,
    ):
        with st.spinner("Строим и проверяем график…"):
            try:
                changed = generate_project(project, start, end, rebuild=rebuild)
            except (CalendarError, ScheduleError, ValueError) as exc:
                st.error(str(exc))
            else:
                _set_project(st.session_state, changed)
                st.rerun()


def _edit_current(project: ScheduleProject, schedule: Schedule) -> None:
    if not schedule.days:
        return
    st.caption(
        "Изменённые назначения закрепляются до снятия пина. После правки выполните проверку."
    )
    with st.form(_key("schedule_edit_form")):
        frame = st.data_editor(
            _schedule_to_edit_df(schedule),
            column_config={
                column: st.column_config.MultiselectColumn(
                    options=[employee.name for employee in schedule.config.employees]
                )
                for column in ("Утро 08–17", "Вечер 15–00", "Ночь 00–08", "Рабочий день")
            },
            disabled=["Дата"],
            use_container_width=True,
            hide_index=True,
            key=_key("schedule_editor"),
        )
        if st.form_submit_button("Применить ручные назначения"):
            try:
                edited = _edit_df_to_schedule(frame, schedule)
                changed = apply_assignments(project, edited.days)
            except ValueError as exc:
                st.error(str(exc))
            else:
                _set_project(st.session_state, changed)
                st.rerun()
    _individual_workday(project)


def _diagnostics(schedule: Schedule) -> None:
    repair = schedule.metadata.get("repair")
    if repair:
        st.write(
            f"Пересчёт от версии {repair['baseline_id'] or 'без ID'}: "
            f"{repair['changed_cells']} изменённых ячеек"
        )
        st.caption(f"Поиск: {repair['search_status']}; доказательство: {repair['optimality']}")
        if repair["changes"]:
            st.dataframe(pd.DataFrame(repair["changes"]), hide_index=True)
    if schedule.status == "ready":
        st.success("Текущая версия прошла обязательные проверки")
    elif schedule.status == "draft":
        st.info("Текущая версия изменена и требует проверки")
    else:
        st.warning("Диагностический черновик: обычный экспорт недоступен")
    search_explanations = {
        "feasible": "Найден допустимый вариант в ограниченное время; "
        "глобальное качество не доказано.",
        "timeout": "Поиск ограничен временем. Проверьте причины ниже или повторите расчёт.",
        "heuristic_exhausted": "Ограниченный поиск не нашёл готовый график; "
        "проверьте данные и доступность.",
        "heuristic_solution": "Найден готовый вариант ограниченным поиском; "
        "глобальное качество не доказано.",
        "pending_approval": "Требуются указанные подтверждения. Откройте раздел подтверждений.",
        "infeasible": "При действующих данных и ограничениях допустимого графика нет.",
    }
    if schedule.search_status in search_explanations:
        st.info(search_explanations[schedule.search_status])
    categories = [
        (
            "Исправить данные",
            lambda item: item.code.startswith(("history_", "calendar_", "norm_", "pin_")),
            "3. История",
        ),
        (
            "Подтвердить разрешённое исключение",
            lambda item: item.code == "approval_required",
            "5. Подтверждения",
        ),
        (
            "Проверить состав и доступность",
            lambda item: item.code in {"coverage", "staffing_unavailable"},
            "2. Ограничения",
        ),
    ]
    for label, match, action in categories:
        problems = [item for item in schedule.diagnostics if match(item)]
        if problems:
            st.write(label)
            for item in problems[:3]:
                st.warning(f"{item.employee_name or ''} {item.date or ''}: {item.detail}")
            actions = {
                "4. Закрепления"
                if item.code.startswith("pin_")
                else "2. Ограничения"
                if item.code.startswith(("calendar_", "norm_"))
                else action
                for item in problems
            }
            for target in sorted(actions):
                if st.button(
                    f"Исправить: {target}",
                    key=f"diagnostics_{schedule.revision_id}_{label}_{target}",
                ):
                    st.session_state["configuration_tabs"] = target
                    st.rerun()
    if schedule.diagnostics:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Дата": item.date,
                        "Сотрудник": item.employee_name,
                        "Причина": item.detail,
                        "Код": item.code,
                        "Подтверждение": item.approval_rule or "",
                        "Значение": item.value,
                    }
                    for item in schedule.diagnostics
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        if any(item.approval_rule for item in schedule.diagnostics):
            st.caption(
                "Допустимые исключения подтверждаются для сотрудника и даты "
                "в разделе «Подтверждения»."
            )


def _next_config(schedule: Schedule) -> Config:
    config = schedule.config.model_copy(deep=True)
    config.month = config.month % 12 + 1
    config.year += config.month == 1
    config.production_calendar = None
    config.carry_over = [
        CarryOverState.model_validate(item) for item in schedule.metadata.get("carry_over", [])
    ]
    config.previous_schedule = schedule.model_copy(deep=True)
    config.previous_schedule.config.previous_schedule = None
    config._quality_origin = "external"
    return config


def _downloads(schedule: Schedule) -> None:
    from duty_schedule.export.pdf import generate_schedule_pdf
    from duty_schedule.export.xls import export_xls
    from duty_schedule.ui.views import render_employee_ics_downloads

    if schedule.status != "ready":
        st.info("Сохранение рабочего проекта доступно и для диагностического черновика.")
        return
    try:
        checked = ensure_exportable(schedule)
    except ExportBlockedError as exc:
        st.error(str(exc))
        return
    digest = hashlib.sha256(checked.model_dump_json().encode()).hexdigest()
    cache = st.session_state.setdefault("ui_exports", {})
    if cache.get("digest") != digest:
        snapshot = checked.config.production_calendar
        short_days = snapshot.short_dates() if snapshot else set()
        with tempfile.TemporaryDirectory() as temporary:
            xls = export_xls(checked, Path(temporary), short_days=short_days).read_bytes()
        try:
            pdf = generate_schedule_pdf(checked, short_days=short_days)
        except (RuntimeError, OSError):
            pdf = None
        cache = {"digest": digest, "xls": xls, "pdf": pdf}
        st.session_state["ui_exports"] = cache
    c1, c2 = st.columns(2)
    c1.download_button(
        "Скачать XLS",
        cache["xls"],
        file_name=f"schedule_{checked.config.year}_{checked.config.month:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )
    if cache["pdf"] is not None:
        c2.download_button(
            "Скачать PDF",
            cache["pdf"],
            file_name=f"schedule_{checked.config.year}_{checked.config.month:02d}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    else:
        c2.caption("PDF недоступен: отсутствуют системные библиотеки WeasyPrint")
    render_employee_ics_downloads(checked)
    next_config = _next_config(checked)
    st.download_button(
        "Скачать конфиг следующего месяца",
        dump_config_yaml(next_config),
        file_name=f"config_{next_config.year}_{next_config.month:02d}.yaml",
        mime="text/yaml",
    )


def _results(project: ScheduleProject) -> None:
    from duty_schedule.ui.views import (
        _render_calendar,
        _render_changelog,
        _render_load_dashboard,
        _render_schedule_diff,
        _render_whatif_panel,
    )

    schedule = current_schedule(project)
    if schedule is None:
        return
    st.subheader(
        f"{MONTHS_RU[schedule.config.month - 1]} {schedule.config.year} · "
        f"текущая версия {schedule.revision_id[:8]}"
    )
    _diagnostics(schedule)
    if st.button("Проверить текущую версию"):
        _set_project(st.session_state, check_current(project))
        st.rerun()
    st.session_state["schedule_history"] = [
        {
            "label": (
                f"{revision.schedule.config.month:02d}.{revision.schedule.config.year} · "
                f"{revision.created_at:%H:%M:%S} · {revision.id[:8]}"
            ),
            "schedule": revision.schedule,
        }
        for revision in project.revisions
    ]
    tabs = st.tabs(
        ["Календарь", "Нагрузка", "Редактирование", "Лог оптимизации", "Сравнение", "Что если?"]
    )
    with tabs[0]:
        _render_calendar(schedule)
    with tabs[1]:
        snapshot = schedule.config.production_calendar
        count = sum(day.kind != "off" for day in snapshot.days) if snapshot else 0
        stats = compute_stats(
            schedule,
            build_assignments(schedule),
            count,
            short_days=snapshot.short_dates() if snapshot else set(),
        )
        _render_load_dashboard(schedule, stats)
    with tabs[2]:
        _edit_current(project, schedule)
    with tabs[3]:
        _render_changelog(schedule)
    with tabs[4]:
        _render_schedule_diff(schedule)
    with tabs[5]:
        snapshot = schedule.config.production_calendar
        _render_whatif_panel(
            schedule,
            snapshot.off_dates() if snapshot else set(),
            snapshot.short_dates() if snapshot else set(),
        )
    _downloads(schedule)


def render_application() -> None:
    if "project" not in st.session_state:
        st.session_state["project"] = new_project(_default_config())
    from duty_schedule.ui.autosave import render_autosave

    render_autosave()
    project = st.session_state["project"]
    _sidebar(project)
    tabs = st.tabs(
        ["1. Состав", "2. Ограничения", "3. История", "4. Закрепления", "5. Подтверждения"],
        key="configuration_tabs",
    )
    with tabs[0]:
        _basic_configuration(project)
        _employee_tools(project)
    with tabs[1]:
        _employee_constraints(project)
        _calendar_configuration(project)
    with tabs[2]:
        _history_configuration(project)
    with tabs[3]:
        _pins_configuration(project)
    with tabs[4]:
        _approval_configuration(project)
    st.caption(
        "Приоритет качества: парные выходные → короткие рабочие серии → "
        "баланс вечеров/ночей → баланс дежурств в нерабочие даты. "
        "Норма выполняется строго по часам."
    )
    _planning(project)
    _results(project)
