from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from duty_schedule.models import (
    CarryOverState,
    Config,
    DaySchedule,
    PinnedAssignment,
    ProductionCalendar,
    Schedule,
    ScheduleDiagnostic,
    ShiftType,
)


class ExportBlockedError(ValueError):
    def __init__(self, diagnostics: list[ScheduleDiagnostic]) -> None:
        self.diagnostics = diagnostics
        super().__init__("График не прошёл обязательные проверки; доступен диагностический проект")


class _CellChange(BaseModel):
    date: date
    employee_id: str
    before: tuple[ShiftType | None, int] | None
    after: tuple[ShiftType | None, int] | None


class _ChangedCells(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changed_cells: int = Field(ge=0)
    changes: list[_CellChange]

    @model_validator(mode="after")
    def consistent_changes(self) -> _ChangedCells:
        if self.changed_cells != len(self.changes):
            raise ValueError("Число правок не соответствует списку изменений")
        if len({(change.date, change.employee_id) for change in self.changes}) != len(self.changes):
            raise ValueError("Повторяющаяся изменённая ячейка")
        return self


class _OptimizationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_id: str | None
    days: dict[date, dict[str, tuple[ShiftType | None, int]]]


class _OptimizationMetadata(_ChangedCells):
    status: str
    algorithm: str
    before: _OptimizationSnapshot
    after: _OptimizationSnapshot
    quality_labels: list[str]
    quality_before: list[float]
    quality_after: list[float]
    optimality: str

    @model_validator(mode="after")
    def consistent_quality(self) -> _OptimizationMetadata:
        if self.status not in {"changes", "no_changes", "log_unavailable"}:
            raise ValueError("Неизвестный статус оптимизации")
        if self.status == "no_changes" and self.changed_cells:
            raise ValueError("Отсутствие изменений не согласовано с числом правок")
        if len(self.quality_before) != len(self.quality_labels) or len(self.quality_after) != len(
            self.quality_labels
        ):
            raise ValueError("Компоненты качества не соответствуют подписям")
        return self


class _RepairMetadata(_ChangedCells):
    baseline_id: str | None
    search_status: str
    optimality: str


def _check_operation_metadata(schedule: Schedule) -> None:
    for key, model in (("optimization", _OptimizationMetadata), ("repair", _RepairMetadata)):
        value = schedule.metadata.get(key)
        if value is not None:
            model.model_validate(value)


def _snapshot_cells(schedule: Schedule) -> dict:
    from duty_schedule.scheduler.postprocess.quality import schedule_cells

    result: dict = {}
    for (day, identity), values in schedule_cells(schedule).items():
        result.setdefault(str(day), {})[identity] = list(values)
    return result


class ScheduleRevision(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    parent_id: str | None = None
    previous_revision_id: str | None = None
    schedule: Schedule
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScheduleProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: int = 1
    id: str = Field(default_factory=lambda: uuid4().hex)
    config: Config
    calendars: list[ProductionCalendar] = []
    revisions: list[ScheduleRevision] = []
    active_revisions: dict[str, str] = {}
    selected_period: str
    repair_candidate: Schedule | None = None

    @model_validator(mode="after")
    def check_references(self) -> ScheduleProject:
        if self.format_version != 1:
            raise ValueError("Неподдерживаемая версия файла проекта")
        ids = [revision.id for revision in self.revisions]
        if len(ids) != len(set(ids)):
            raise ValueError("Повторяющийся ID версии")
        by_id = {revision.id: revision for revision in self.revisions}
        for period in [self.selected_period, *self.active_revisions]:
            parsed = datetime.strptime(period, "%Y-%m")
            if parsed.strftime("%Y-%m") != period:
                raise ValueError("Неверный период проекта")
        for revision in self.revisions:
            for reference in (revision.parent_id, revision.previous_revision_id):
                if reference is not None and (reference not in by_id or reference == revision.id):
                    raise ValueError("Неизвестная родительская версия")
            period = _period(revision.schedule.config)
            for reference, expected_period in (
                (revision.parent_id, period),
                (revision.previous_revision_id, _previous_period(period)),
            ):
                if (
                    reference is not None
                    and _period(by_id[reference].schedule.config) != expected_period
                ):
                    raise ValueError("Родительская версия относится к другому периоду")
        pending = {
            revision.id: {ref for ref in (revision.parent_id, revision.previous_revision_id) if ref}
            for revision in self.revisions
        }
        dependents: dict[str, list[str]] = {revision_id: [] for revision_id in ids}
        for revision_id, parents in pending.items():
            for parent in parents:
                dependents[parent].append(revision_id)
        available = [revision_id for revision_id, parents in pending.items() if not parents]
        visited = 0
        while available:
            parent = available.pop()
            visited += 1
            for dependent in dependents[parent]:
                pending[dependent].discard(parent)
                if not pending[dependent]:
                    available.append(dependent)
        if visited != len(ids):
            raise ValueError("История версий содержит цикл")
        for period, revision_id in self.active_revisions.items():
            active_revision = by_id.get(revision_id)
            if active_revision is None or _period(active_revision.schedule.config) != period:
                raise ValueError("Активная версия не соответствует периоду проекта")
            if (
                active_revision.previous_revision_id is not None
                and _previous_period(period) not in self.active_revisions
            ):
                raise ValueError("Отсутствует активная версия связанного предыдущего месяца")
        return self


def _period(config: Config) -> str:
    return f"{config.year:04d}-{config.month:02d}"


def _previous_period(period: str) -> str:
    year, month = map(int, period.split("-"))
    return f"{year - 1:04d}-12" if month == 1 else f"{year:04d}-{month - 1:02d}"


def new_project(config: Config) -> ScheduleProject:
    return ScheduleProject(config=config.model_copy(deep=True), selected_period=_period(config))


def current_schedule(project: ScheduleProject) -> Schedule | None:
    active_id = project.active_revisions.get(project.selected_period)
    schedule = next((r.schedule for r in project.revisions if r.id == active_id), None)
    if schedule is None:
        return None
    schedule = schedule.model_copy(deep=True)
    problems = _dependency_diagnostics(project, schedule)
    if not problems:
        return schedule
    result = schedule.model_copy(deep=True)
    result.status = "diagnostic"
    result.diagnostics = [*result.diagnostics, *problems]
    return result


def _dependency_diagnostics(
    project: ScheduleProject, schedule: Schedule
) -> list[ScheduleDiagnostic]:
    from duty_schedule.scheduler.validation import validate_schedule_result

    by_id = {revision.id: revision for revision in project.revisions}
    ancestors: list[Schedule] = []
    period = _period(schedule.config)
    while period in project.active_revisions:
        revision = by_id[project.active_revisions[period]]
        previous_period = _previous_period(period)
        if (
            revision.previous_revision_id is not None
            and previous_period not in project.active_revisions
        ):
            return [
                ScheduleDiagnostic(
                    code="previous_revision_changed",
                    detail="Отсутствует текущая версия связанного предыдущего месяца",
                )
            ]
        period = previous_period
    period = _previous_period(_period(schedule.config))
    while period in project.active_revisions:
        ancestors.append(by_id[project.active_revisions[period]].schedule)
        period = _previous_period(period)
    previous = None
    for ancestor in reversed(ancestors):
        checked = validate_schedule_result(ancestor)
        problems = _carry_dependency_diagnostics(ancestor, previous)
        stale = any(d.code == "previous_revision_changed" for d in ancestor.diagnostics)
        if ancestor.status != "ready" or problems or stale:
            checked.status = "diagnostic"
        previous = checked
    return _carry_dependency_diagnostics(schedule, previous)


def _carry_dependency_diagnostics(
    schedule: Schedule, previous: Schedule | None
) -> list[ScheduleDiagnostic]:
    if previous is None:
        return []
    mismatch = previous.status != "ready"
    actual = {c.employee_id or c.employee_name: c for c in schedule.config.carry_over}
    for raw in previous.metadata.get("carry_over", []):
        expected = raw if isinstance(raw, CarryOverState) else CarryOverState.model_validate(raw)
        current = actual.get(expected.employee_id or expected.employee_name)
        if current is None:
            current = next(
                (c for c in actual.values() if c.employee_name == expected.employee_name), None
            )
        if current is None:
            continue
        fields = (
            "last_shift",
            "consecutive_working",
            "consecutive_off",
            "consecutive_same_shift",
            "as_of",
        )
        if any(getattr(current, key) != getattr(expected, key) for key in fields):
            mismatch = True
    if not mismatch:
        return []
    return [
        ScheduleDiagnostic(
            code="previous_revision_changed",
            detail="Перенос не соответствует текущей проверенной версии предыдущего месяца",
        )
    ]


def _input_key(schedule: Schedule) -> str:
    return json.dumps(
        {
            "config": schedule.config.model_dump(mode="json"),
            "days": [day.model_dump(mode="json") for day in schedule.days],
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def _append_revision(project: ScheduleProject, schedule: Schedule) -> ScheduleProject:
    result = project.model_copy(deep=True)
    period = _period(schedule.config)
    old_id = result.active_revisions.get(period)
    old = next((r.schedule for r in result.revisions if r.id == old_id), None)
    changed = old is None or _input_key(old) != _input_key(schedule)
    revision = ScheduleRevision(
        parent_id=result.active_revisions.get(period),
        previous_revision_id=result.active_revisions.get(_previous_period(period)),
        schedule=schedule.model_copy(deep=True),
    )
    revision.schedule.revision_id = revision.id
    snapshot = revision.schedule.config.previous_schedule
    source_id = revision.previous_revision_id
    if snapshot is not None and source_id is not None:
        source = next(r.schedule for r in result.revisions if r.id == source_id)
        same_input = (
            snapshot.config.model_dump(exclude={"previous_schedule"})
            == source.config.model_dump(exclude={"previous_schedule"})
            and snapshot.days == source.days
        )
        if snapshot.revision_id == source_id and same_input and source.status == "ready":
            revision.schedule.config._quality_origin = "project"
            revision.schedule.config._quality_state = "available"
        else:
            revision.schedule.config._quality_state = "stale"
            revision.schedule.status = "diagnostic"
            if not any(
                d.code == "previous_revision_changed" for d in revision.schedule.diagnostics
            ):
                revision.schedule.diagnostics.append(
                    ScheduleDiagnostic(
                        code="previous_revision_changed",
                        detail="Предыдущий месяц изменён; требуется обновить перенос и пересчитать",
                    )
                )
    optimization = revision.schedule.metadata.get("optimization")
    if (
        optimization
        and optimization["after"]["revision_id"] is None
        and optimization["after"]["days"] == _snapshot_cells(revision.schedule)
    ):
        optimization["after"]["revision_id"] = revision.id
    result.revisions.append(revision)
    result.active_revisions[period] = revision.id
    result.selected_period = period
    result.config = revision.schedule.config.model_copy(deep=True)
    calendar = schedule.config.production_calendar
    if calendar is not None:
        result.calendars = [
            c for c in result.calendars if (c.year, c.month) != (calendar.year, calendar.month)
        ] + [calendar.model_copy(deep=True)]
    for later_period, later_id in list(result.active_revisions.items()):
        if later_period <= period or not changed:
            continue
        later = next(r for r in result.revisions if r.id == later_id)
        stale = later.schedule.model_copy(deep=True)
        stale.config._quality_state = "stale"
        stale.status = "diagnostic"
        stale.diagnostics = [
            ScheduleDiagnostic(
                code="previous_revision_changed",
                detail="Предыдущий месяц изменён; требуется обновить перенос и пересчитать",
            )
        ]
        invalidated = ScheduleRevision(
            parent_id=later.id,
            previous_revision_id=result.active_revisions.get(_previous_period(later_period)),
            schedule=stale,
        )
        invalidated.schedule.revision_id = invalidated.id
        result.revisions.append(invalidated)
        result.active_revisions[later_period] = invalidated.id
    return result


def add_revision(project: ScheduleProject, schedule: Schedule) -> ScheduleProject:
    from duty_schedule.scheduler.validation import validate_schedule_result

    return _append_revision(project, validate_schedule_result(schedule))


def ensure_exportable(schedule: Schedule) -> Schedule:
    from duty_schedule.scheduler.validation import validate_schedule_result

    stale = [d for d in schedule.diagnostics if d.code == "previous_revision_changed"]
    if stale:
        raise ExportBlockedError(stale)
    checked = validate_schedule_result(schedule)
    if checked.status != "ready":
        raise ExportBlockedError(checked.diagnostics)
    return checked


def _state(day: DaySchedule, name: str) -> ShiftType:
    return next(
        (shift for shift in ShiftType if name in getattr(day, shift.value)), ShiftType.DAY_OFF
    )


def apply_assignments(project: ScheduleProject, days: list[DaySchedule]) -> ScheduleProject:
    previous = current_schedule(project)
    if previous is None:
        raise ValueError("Нет текущего графика для правки")
    edited = previous.model_copy(deep=True)
    edited.days = [day.model_copy(deep=True) for day in days]
    before = {day.date: day for day in previous.days}
    pins = {(pin.date, pin.employee_name): pin for pin in edited.config.pins}
    for day in edited.days:
        old = before.get(day.date, DaySchedule(date=day.date))
        for employee in edited.config.employees:
            name = employee.name
            shift = _state(day, name)
            hours = day.workday_hours.get(name)
            if shift == _state(old, name) and hours == old.workday_hours.get(name):
                continue
            if shift in (ShiftType.VACATION, ShiftType.SICK_LEAVE):
                continue
            pins[(day.date, name)] = PinnedAssignment(
                date=day.date, employee_name=name, shift=shift, working_hours=hours
            )
    edited.config.pins = list(pins.values())
    edited.status = "draft"
    edited.diagnostics = []
    edited.metadata.pop("carry_over", None)
    return _append_revision(project, edited)


def update_config(project: ScheduleProject, config: Config) -> ScheduleProject:
    target = project.model_copy(deep=True)
    target.selected_period = _period(config)
    previous = current_schedule(target)
    if previous is None:
        result = project.model_copy(deep=True)
        result.config = config.model_copy(deep=True)
        result.selected_period = _period(config)
        return result
    names_by_id = {e.employee_id: e.name for e in config.employees}
    rename = {e.name: names_by_id.get(e.employee_id, e.name) for e in previous.config.employees}
    edited = previous.model_copy(deep=True)
    edited.config = config.model_copy(deep=True)
    for day in edited.days:
        for shift in ShiftType:
            setattr(
                day, shift.value, [rename.get(name, name) for name in getattr(day, shift.value)]
            )
        day.workday_hours = {
            rename.get(name, name): hours for name, hours in day.workday_hours.items()
        }
    for references in (
        edited.config.pins,
        edited.config.carry_over,
        edited.config.approvals,
        edited.config.norm_choices,
    ):
        for reference in references:
            reference.employee_name = rename.get(reference.employee_name, reference.employee_name)
    edited.status = "draft"
    edited.diagnostics = []
    edited.metadata.pop("carry_over", None)
    return _append_revision(project, edited)


def remove_pin(project: ScheduleProject, day: date, employee_name: str) -> ScheduleProject:
    config = project.config.model_copy(deep=True)
    config.pins = [
        pin for pin in config.pins if (pin.date, pin.employee_name) != (day, employee_name)
    ]
    return update_config(project, config)


def check_current(project: ScheduleProject) -> ScheduleProject:
    from duty_schedule.scheduler.validation import validate_schedule_result

    current = current_schedule(project)
    if current is None:
        raise ValueError("Нет графика для проверки")
    stale = [d for d in current.diagnostics if d.code == "previous_revision_changed"]
    checked = validate_schedule_result(current)
    if stale:
        checked.status = "diagnostic"
        checked.diagnostics.extend(stale)
    if _input_key(current) == _input_key(checked):
        result = project.model_copy(deep=True)
        revision = next(item for item in result.revisions if item.id == current.revision_id)
        checked.revision_id = revision.id
        revision.schedule = checked
        return result
    return _append_revision(project, checked)


def serialize_project(project: ScheduleProject) -> bytes:
    return project.model_dump_json(indent=2).encode("utf-8")


def load_project(content: bytes | str) -> ScheduleProject:
    from duty_schedule.scheduler.changelog import ChangeLog
    from duty_schedule.scheduler.validation import validate_schedule_result

    try:
        raw = json.loads(content)
        project = ScheduleProject.model_validate(raw)
        for revision in project.revisions:
            _check_operation_metadata(revision.schedule)
            changelog = revision.schedule.metadata.get("changelog")
            if changelog is not None:
                revision.schedule.metadata["changelog"] = TypeAdapter(ChangeLog).validate_python(
                    changelog
                )
    except (ValueError, TypeError) as exc:
        raise ValueError("Некорректный файл рабочего проекта") from exc
    for revision in project.revisions:
        stale = [d for d in revision.schedule.diagnostics if d.code == "previous_revision_changed"]
        revision.schedule = validate_schedule_result(revision.schedule)
        if stale:
            revision.schedule.status = "diagnostic"
            revision.schedule.diagnostics.extend(stale)
    if project.repair_candidate is not None:
        _check_operation_metadata(project.repair_candidate)
        project.repair_candidate = validate_schedule_result(project.repair_candidate)
    by_id = {revision.id: revision for revision in project.revisions}
    for period in sorted(project.active_revisions):
        revision = by_id[project.active_revisions[period]]
        problems = _dependency_diagnostics(project, revision.schedule)
        if problems:
            revision.schedule.status = "diagnostic"
            revision.schedule.diagnostics.extend(problems)
    for period, active_id in project.active_revisions.items():
        revision = by_id[active_id]
        previous_id = project.active_revisions.get(_previous_period(period))
        snapshot = revision.schedule.config.previous_schedule
        if snapshot is not None and previous_id is not None:
            active_previous = by_id[previous_id].schedule
            same_input = (
                snapshot.config.model_dump(exclude={"previous_schedule"})
                == active_previous.config.model_dump(exclude={"previous_schedule"})
                and snapshot.days == active_previous.days
            )
            if (
                snapshot.revision_id == previous_id
                and same_input
                and active_previous.status == "ready"
                and not any(
                    item.code == "previous_revision_changed"
                    for item in revision.schedule.diagnostics
                )
            ):
                revision.schedule.config._quality_origin = "project"
            else:
                revision.schedule.config._quality_state = "stale"
    return project
