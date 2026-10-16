from __future__ import annotations

import json
from collections.abc import MutableMapping
from datetime import date
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from duty_schedule.models import City, Config, Employee, ScheduleType
from duty_schedule.project import ScheduleProject, new_project


class PersonnelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")

    employee_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    name: str = Field(min_length=1)
    city: City
    schedule_type: ScheduleType | None = None
    on_duty: StrictBool | None = None

    @model_validator(mode="after")
    def validate_name(self) -> PersonnelEntry:
        if (
            not self.name.strip()
            or self.name != self.name.strip()
            or len(self.name.splitlines()) != 1
        ):
            raise ValueError("Имя сотрудника должно быть непустой строкой без внешних пробелов")
        return self


def _next_period() -> date:
    today = date.today()
    return date(today.year + (today.month == 12), today.month % 12 + 1, 1)


class OnboardingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    year: int = Field(default_factory=lambda: _next_period().year, ge=2024, le=9999)
    month: int = Field(default_factory=lambda: _next_period().month, ge=1, le=12)
    employees: list[PersonnelEntry] = []
    stage: Literal["personnel", "roles"] = "personnel"

    @model_validator(mode="after")
    def unique_personnel(self) -> OnboardingDraft:
        for field in ("name", "employee_id"):
            values = [getattr(employee, field) for employee in self.employees]
            if len(values) != len(set(values)):
                raise ValueError("Повторяющиеся имена или ID сотрудников не допускаются")
        return self


class DraftSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["personnel_draft"] = "personnel_draft"
    version: Literal[1] = 1
    draft: OnboardingDraft


def serialize_draft(draft: OnboardingDraft) -> str:
    return DraftSnapshot(draft=draft).model_dump_json()


def load_draft(content: str | bytes) -> OnboardingDraft:
    return DraftSnapshot.model_validate_json(content).draft


def add_personnel(draft: OnboardingDraft, city: City, name: str) -> OnboardingDraft:
    name = name.strip()
    if not name or len(name.splitlines()) != 1:
        raise ValueError("Укажите имя одного сотрудника")
    if name in {employee.name for employee in draft.employees}:
        raise ValueError(f"Сотрудник «{name}» уже внесён в персонал")
    employee = PersonnelEntry(name=name, city=city)
    return OnboardingDraft.model_validate(
        {**draft.model_dump(), "employees": [*draft.employees, employee]}
    )


def remove_personnel(draft: OnboardingDraft, employee_id: str) -> OnboardingDraft:
    if employee_id not in {employee.employee_id for employee in draft.employees}:
        raise ValueError("Неизвестный сотрудник")
    employees = [employee for employee in draft.employees if employee.employee_id != employee_id]
    return OnboardingDraft.model_validate(
        {
            **draft.model_dump(),
            "employees": employees,
            "stage": draft.stage if employees else "personnel",
        }
    )


def apply_city_lists(draft: OnboardingDraft, moscow: str, khabarovsk: str) -> OnboardingDraft:
    existing = {employee.name: employee for employee in draft.employees}
    employees = []
    for city, content in ((City.MOSCOW, moscow), (City.KHABAROVSK, khabarovsk)):
        for line in content.splitlines():
            name = line.strip()
            if not name:
                continue
            previous = existing.get(name)
            employee = (
                previous.model_copy(update={"city": city}, deep=True)
                if previous is not None
                else PersonnelEntry(name=name, city=city)
            )
            employees.append(employee)
    if not employees:
        raise ValueError("Внесите хотя бы одного сотрудника")
    return OnboardingDraft.model_validate({**draft.model_dump(), "employees": employees})


def assign_roles(
    draft: OnboardingDraft,
    employee_ids: list[str],
    schedule_type: ScheduleType | None = None,
    on_duty: bool | None = None,
    *,
    replace: bool = False,
) -> OnboardingDraft:
    identities = set(employee_ids)
    if not identities or not identities <= {e.employee_id for e in draft.employees}:
        raise ValueError("Выберите существующих сотрудников")
    changes: dict[str, Any] = {}
    if replace or schedule_type is not None:
        changes["schedule_type"] = schedule_type
    if replace or on_duty is not None:
        changes["on_duty"] = on_duty
    employees = [
        e.model_copy(update=changes, deep=True) if e.employee_id in identities else e
        for e in draft.employees
    ]
    return OnboardingDraft.model_validate({**draft.model_dump(), "employees": employees})


def pending_personnel(draft: OnboardingDraft, city: City | None = None) -> list[PersonnelEntry]:
    return [
        employee
        for employee in draft.employees
        if (employee.schedule_type is None or employee.on_duty is None)
        and (city is None or employee.city == city)
    ]


def assign_pending_roles(
    draft: OnboardingDraft,
    employee_ids: list[str],
    schedule_type: ScheduleType | None = None,
    on_duty: bool | None = None,
) -> OnboardingDraft:
    if not employee_ids or not set(employee_ids) <= {
        employee.employee_id for employee in pending_personnel(draft)
    }:
        raise ValueError("Выберите сотрудников без полного назначения")
    return assign_roles(draft, employee_ids, schedule_type, on_duty)


def rename_personnel(draft: OnboardingDraft, employee_id: str, name: str) -> OnboardingDraft:
    if employee_id not in {e.employee_id for e in draft.employees}:
        raise ValueError("Неизвестный сотрудник")
    employees = [
        e.model_copy(update={"name": name.strip()}, deep=True)
        if e.employee_id == employee_id
        else e
        for e in draft.employees
    ]
    return OnboardingDraft.model_validate({**draft.model_dump(), "employees": employees})


def incomplete_roles(draft: OnboardingDraft) -> list[str]:
    issues = []
    for employee in draft.employees:
        fields = []
        if employee.schedule_type is None:
            fields.append("график")
        if employee.on_duty is None:
            fields.append("участие в дежурствах")
        if fields:
            issues.append(f"{employee.name}: {', '.join(fields)}")
    return issues


def city_counts(draft: OnboardingDraft, city: City) -> dict[str, int]:
    employees = [e for e in draft.employees if e.city == city]
    return {
        "total": len(employees),
        "five_two": sum(e.schedule_type == ScheduleType.FIVE_TWO for e in employees),
        "flexible": sum(e.schedule_type == ScheduleType.FLEXIBLE for e in employees),
        "on_duty": sum(e.on_duty is True for e in employees),
        "incomplete": sum(e.on_duty is None or e.schedule_type is None for e in employees),
    }


def draft_to_config(draft: OnboardingDraft) -> Config:
    if not draft.employees:
        raise ValueError("Внесите персонал на шаге 0")
    issues = incomplete_roles(draft)
    if issues:
        raise ValueError("Не настроено: " + "; ".join(issues))
    return Config(
        year=draft.year,
        month=draft.month,
        employees=[Employee.model_validate(employee.model_dump()) for employee in draft.employees],
    )


def complete_onboarding(state: MutableMapping[Any, Any]) -> ScheduleProject:
    draft = state["onboarding_draft"]
    project = new_project(draft_to_config(draft))
    project.id = draft.id
    state["project"] = project
    state["ui_epoch"] = int(state.get("ui_epoch", 0)) + 1
    return project


def start_new_onboarding(state: MutableMapping[Any, Any]) -> None:
    state["onboarding_draft"] = OnboardingDraft()
    state.pop("project", None)
    state.pop("roster_draft", None)
    state["autosave_token"] = None
    state["autosave_status"] = "saving"
    state["ui_epoch"] = int(state.get("ui_epoch", 0)) + 1
    state.pop("ui_import_notice", None)
    state.pop("ui_exports", None)


def import_draft_into_state(state: MutableMapping[Any, Any], content: str | bytes) -> None:
    draft = load_draft(content)
    state.pop("roster_draft", None)
    state["onboarding_draft"] = draft
    state.pop("project", None)
    state["ui_epoch"] = int(state.get("ui_epoch", 0)) + 1


def storage_snapshot(state: MutableMapping[Any, Any]) -> tuple[str, str]:
    from duty_schedule.project import serialize_project

    if "roster_draft" in state:
        from duty_schedule.ui.roster import roster_config, serialize_roster

        draft = state["roster_draft"]
        project = state.get("project")
        if project is not None:
            try:
                checked = roster_config(draft, project)
            except ValueError:
                pass
            else:
                if checked.model_dump(mode="json") == project.config.model_dump(mode="json"):
                    return serialize_project(project).decode(), project.id
        return serialize_roster(draft, project), draft.id
    if "project" in state:
        project = state["project"]
        return serialize_project(project).decode(), project.id
    draft = state["onboarding_draft"]
    return serialize_draft(draft), draft.id


def restore_snapshot(state: MutableMapping[Any, Any], content: str | bytes) -> None:
    from duty_schedule.project import load_project

    raw = json.loads(content)
    if not isinstance(raw, dict):
        raise ValueError("Запись должна содержать объект проекта или подготовки")
    if raw.get("kind") == "roster_draft":
        from duty_schedule.ui.roster import load_roster

        draft, project = load_roster(content)
        state["roster_draft"] = draft
        state.pop("onboarding_draft", None)
        if project is None:
            state.pop("project", None)
        else:
            state["project"] = project
    elif "kind" in raw:
        restored_draft = load_draft(content)
        state.pop("roster_draft", None)
        state["onboarding_draft"] = restored_draft
        state.pop("project", None)
    else:
        restored_project = load_project(content)
        state.pop("roster_draft", None)
        state["project"] = restored_project
        state.pop("onboarding_draft", None)
    state["ui_epoch"] = int(state.get("ui_epoch", 0)) + 1
