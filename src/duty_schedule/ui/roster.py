from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any
from uuid import uuid4

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from duty_schedule.models import City, Config, Employee, ScheduleType, ShiftType
from duty_schedule.project import ScheduleProject, load_project, serialize_project
from duty_schedule.ui.config_io import config_from_tables, config_to_tables, employees_from_table
from duty_schedule.ui.mappings import (
    _CITY_TO_RU,
    _RU_TO_CITY,
    _RU_TO_SHIFT,
    _RU_TO_STYPE,
    _SHIFT_TO_RU,
    _STYPE_TO_RU,
)


class RosterRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    name: str = ""
    city: City | None = None
    schedule_type: ScheduleType | None = None
    on_duty: StrictBool | None = None
    always_on_duty: StrictBool = False
    morning_only: StrictBool = False
    evening_only: StrictBool = False
    preferred_shift: ShiftType | None = None
    max_consecutive_working: int | None = None


class RosterDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    year: int = Field(ge=2024, le=9999)
    month: int = Field(ge=1, le=12)
    rows: list[RosterRow] = []

    @model_validator(mode="after")
    def unique_ids(self) -> RosterDraft:
        ids = [row.employee_id for row in self.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("Повторяющиеся ID строк")
        return self


def from_project(project: ScheduleProject) -> RosterDraft:
    return RosterDraft(
        id=project.id,
        year=project.config.year,
        month=project.config.month,
        rows=[
            RosterRow.model_validate(
                {
                    key: value
                    for key, value in employee.model_dump().items()
                    if key in RosterRow.model_fields
                }
            )
            for employee in project.config.employees
        ],
    )


def initialize_roster(state: MutableMapping[Any, Any]) -> None:
    if "roster_draft" in state:
        return
    if "project" in state:
        state["roster_draft"] = from_project(state["project"])
    else:
        from duty_schedule.ui.onboarding import OnboardingDraft

        legacy = state.pop("onboarding_draft", None) or OnboardingDraft()
        state["roster_draft"] = RosterDraft(
            id=legacy.id,
            year=legacy.year,
            month=legacy.month,
            rows=[RosterRow.model_validate(employee.model_dump()) for employee in legacy.employees],
        )


def row_frame(draft: RosterDraft) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": row.employee_id,
                "Имя": row.name,
                "Город": _CITY_TO_RU[row.city] if row.city else "",
                "График": _STYPE_TO_RU[row.schedule_type] if row.schedule_type else "",
                "Дежурный": "" if row.on_duty is None else ("Да" if row.on_duty else "Нет"),
                "Всегда на деж.": row.always_on_duty,
                "Только утро": row.morning_only,
                "Только вечер": row.evening_only,
                "Предпочт. смена": _SHIFT_TO_RU[row.preferred_shift]
                if row.preferred_shift
                else None,
                "Макс. подряд": row.max_consecutive_working,
            }
            for row in draft.rows
        ],
        columns=[
            "ID",
            "Имя",
            "Город",
            "График",
            "Дежурный",
            "Всегда на деж.",
            "Только утро",
            "Только вечер",
            "Предпочт. смена",
            "Макс. подряд",
        ],
    )


def rows_from_frame(frame: pd.DataFrame) -> list[RosterRow]:
    def value(raw: Any) -> Any:
        return None if raw is None or pd.isna(raw) else raw

    rows = []
    for raw in frame.to_dict("records"):
        data = {key: value(val) for key, val in raw.items()}
        rows.append(
            RosterRow(
                employee_id=data["ID"],
                name=data["Имя"] or "",
                city=City(_RU_TO_CITY[data["Город"]]) if data["Город"] else None,
                schedule_type=ScheduleType(_RU_TO_STYPE[data["График"]])
                if data["График"]
                else None,
                on_duty={"Да": True, "Нет": False}.get(data["Дежурный"]),
                always_on_duty=bool(data["Всегда на деж."]),
                morning_only=bool(data["Только утро"]),
                evening_only=bool(data["Только вечер"]),
                preferred_shift=_RU_TO_SHIFT.get(data["Предпочт. смена"]),
                max_consecutive_working=data["Макс. подряд"],
            )
        )
    return rows


def apply_delta(
    seed: RosterDraft, changes: dict[str, Any], added_ids: dict[int, str]
) -> RosterDraft:
    records = row_frame(seed).to_dict("records")
    for index, values in changes.get("edited_rows", {}).items():
        records[int(index)].update({key: val for key, val in values.items() if key != "ID"})
    deleted = set(changes.get("deleted_rows", []))
    records = [row for index, row in enumerate(records) if index not in deleted]
    for index, values in enumerate(changes.get("added_rows", [])):
        identity = added_ids.setdefault(index, uuid4().hex)
        blank = row_frame(
            seed.model_copy(update={"rows": [RosterRow(employee_id=identity)]})
        ).to_dict("records")[0]
        blank.update({key: val for key, val in values.items() if key != "ID"})
        records.append(blank)
    frame = pd.DataFrame(records, columns=row_frame(seed).columns)
    return RosterDraft.model_validate({**seed.model_dump(), "rows": rows_from_frame(frame)})


def copy_row(draft: RosterDraft, identity: str) -> RosterDraft:
    source = next((row for row in draft.rows if row.employee_id == identity), None)
    if source is None:
        raise ValueError("Выберите существующую строку")
    copied = source.model_copy(update={"employee_id": uuid4().hex, "name": ""}, deep=True)
    return draft.model_copy(update={"rows": [*draft.rows, copied]}, deep=True)


def row_issues(draft: RosterDraft) -> list[str]:
    issues = []
    if not draft.rows:
        return ["Добавьте сотрудников в состав"]
    names: set[str] = set()
    for index, row in enumerate(draft.rows, 1):
        missing = []
        if not row.name.strip():
            missing.append("имя")
        elif row.name != row.name.strip() or len(row.name.splitlines()) != 1:
            missing.append("имя без переносов строк и внешних пробелов")
        elif row.name in names:
            missing.append("уникальное имя")
        names.add(row.name)
        for field, label in (
            ("city", "город"),
            ("schedule_type", "график"),
            ("on_duty", "участие в дежурствах"),
        ):
            if getattr(row, field) is None:
                missing.append(label)
        if not missing:
            try:
                Employee.model_validate(row.model_dump())
            except ValueError as exc:
                issues.append(f"Строка {index} ({row.name}): {exc}")
        if missing:
            issues.append(
                f"Строка {index} ({row.name or 'без имени'}): укажите {', '.join(missing)}"
            )
    return issues


def roster_config(draft: RosterDraft, project: ScheduleProject | None = None) -> Config:
    issues = row_issues(draft)
    if issues:
        raise ValueError("\n".join(issues))
    frame = row_frame(draft)
    frame["Дежурный"] = [row.on_duty for row in draft.rows]
    if project is None:
        return Config(year=draft.year, month=draft.month, employees=employees_from_table(frame))
    base = project.config
    tables = config_to_tables(base)
    updated = config_from_tables(frame, base, tables.employee_dates)
    data = updated.model_dump()
    data.update(year=draft.year, month=draft.month)
    if (draft.year, draft.month) != (base.year, base.month):
        from duty_schedule.ui.components import _saved_calendar

        data["production_calendar"] = _saved_calendar(project, draft.year, draft.month)
    return Config.model_validate(data)


def serialize_roster(draft: RosterDraft, project: ScheduleProject | None) -> str:
    return json.dumps(
        {
            "kind": "roster_draft",
            "version": 1,
            "draft": draft.model_dump(mode="json"),
            "project": json.loads(serialize_project(project)) if project else None,
        },
        ensure_ascii=False,
    )


def load_roster(content: str | bytes) -> tuple[RosterDraft, ScheduleProject | None]:
    raw = json.loads(content)
    if (
        not isinstance(raw, dict)
        or set(raw) != {"kind", "version", "draft", "project"}
        or raw["kind"] != "roster_draft"
        or type(raw["version"]) is not int
        or raw["version"] != 1
    ):
        raise ValueError("Неверный формат черновика состава")
    draft = RosterDraft.model_validate(raw["draft"])
    project = load_project(json.dumps(raw["project"])) if raw["project"] is not None else None
    if project and project.id != draft.id:
        raise ValueError("Черновик и проект должны иметь один ID")
    return draft, project
