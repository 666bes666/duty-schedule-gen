"""Модели данных: сотрудники, конфигурация, расписание."""

from __future__ import annotations

import calendar as month_calendar
from datetime import UTC, date, datetime
from datetime import date as Date
from enum import StrEnum
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field, model_validator


class ScheduleType(StrEnum):
    FLEXIBLE = "flexible"
    FIVE_TWO = "5/2"


class OptimizationPriority(StrEnum):
    ISOLATED_WEEKENDS = "isolated_weekends"
    EVENING_SHIFTS = "evening_shifts"
    CONSECUTIVE_DAYS = "consecutive_days"
    WEEKEND_DAYS = "weekend_days"


class ShiftType(StrEnum):
    MORNING = "morning"
    EVENING = "evening"
    NIGHT = "night"
    WORKDAY = "workday"
    DAY_OFF = "day_off"
    VACATION = "vacation"
    SICK_LEAVE = "sick_leave"


class City(StrEnum):
    MOSCOW = "moscow"
    KHABAROVSK = "khabarovsk"


SHIFT_START = {
    ShiftType.MORNING: (8, 0),
    ShiftType.EVENING: (15, 0),
    ShiftType.NIGHT: (0, 0),
    ShiftType.WORKDAY: (9, 0),
}
SHIFT_END = {
    ShiftType.MORNING: (17, 0),
    ShiftType.EVENING: (0, 0),
    ShiftType.NIGHT: (8, 0),
    ShiftType.WORKDAY: (18, 0),
}

SHIFT_NAMES_RU = {
    ShiftType.MORNING: "Утро",
    ShiftType.EVENING: "Вечер",
    ShiftType.NIGHT: "Ночь",
    ShiftType.WORKDAY: "Рабочий день",
    ShiftType.DAY_OFF: "Выходной",
    ShiftType.VACATION: "Отпуск",
    ShiftType.SICK_LEAVE: "Больничный",
}


class CalendarDay(BaseModel):
    date: date
    kind: Literal["working", "off", "short"]


class ProductionCalendar(BaseModel):
    year: int = Field(ge=2024, le=9999)
    month: int = Field(ge=1, le=12)
    days: list[CalendarDay]
    source: str = Field(min_length=1)
    fetched_at: datetime
    verified: bool = True
    used_saved: bool = False

    @model_validator(mode="after")
    def validate_period(self) -> ProductionCalendar:
        expected = {
            date(self.year, self.month, d)
            for d in range(1, month_calendar.monthrange(self.year, self.month)[1] + 1)
        }
        actual = [d.date for d in self.days]
        if len(actual) != len(expected) or set(actual) != expected:
            raise ValueError("Календарь должен содержать каждую дату месяца ровно один раз")
        return self

    def is_working(self, day: date) -> bool:
        return self.hours(day) > 0

    def hours(self, day: date) -> int:
        record = next((record for record in self.days if record.date == day), None)
        if record is None:
            raise ValueError(f"Дата {day} отсутствует в производственном календаре")
        return {"working": 8, "short": 7, "off": 0}[record.kind]

    def off_dates(self) -> set[date]:
        return {record.date for record in self.days if record.kind == "off"}

    def short_dates(self) -> set[date]:
        return {record.date for record in self.days if record.kind == "short"}


class NormChoice(BaseModel):
    employee_name: str
    employee_id: str | None = None
    year: int = Field(ge=2024, le=9999)
    month: int = Field(ge=1, le=12)
    mode: Literal["adjusted", "full"] = "adjusted"


class RuleApproval(BaseModel):
    employee_name: str
    employee_id: str | None = None
    date: date
    rule: Literal["working_streak", "weekly_day_off", "individual_workday"]
    purpose: Literal["coverage", "monthly_norm"]
    value: int | None = None
    confirmed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_value(self) -> RuleApproval:
        if self.rule == "working_streak" and (self.value is None or not 1 <= self.value <= 7):
            raise ValueError("Подтверждение серии должно задавать предел от 1 до 7")
        if self.rule == "individual_workday" and (self.value is None or not 1 <= self.value <= 8):
            raise ValueError("Подтверждение индивидуального Р должно задавать от 1 до 8 часов")
        if self.rule == "weekly_day_off" and self.value is not None:
            raise ValueError("Подтверждение еженедельного выходного не имеет значения value")
        return self


class MonthlyTarget(BaseModel):
    calendar_hours: int
    absence_reduction_hours: int
    adjusted_hours: int
    selected_hours: int
    mode: Literal["adjusted", "full"] = "adjusted"


class ScheduleDiagnostic(BaseModel):
    code: str
    detail: str
    employee_name: str | None = None
    date: Date | None = None
    approval_rule: Literal["working_streak", "weekly_day_off", "individual_workday"] | None = None
    value: int | None = None


class VacationPeriod(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def end_after_start(self) -> VacationPeriod:
        if self.end < self.start:
            raise ValueError("Дата окончания отпуска должна быть не раньше даты начала")
        return self


class Employee(BaseModel):
    """Сотрудник: обычный предел серии 6, персональный предел сохраняется.

    Цель 5 рабочих дней относится к качеству, а серия до 7 требует
    отдельного подтверждения конкретной даты и сотрудника.
    """

    name: str
    employee_id: str = ""
    city: City
    schedule_type: ScheduleType
    on_duty: bool = True
    always_on_duty: bool = False
    morning_only: bool = False
    evening_only: bool = False
    vacations: list[VacationPeriod] = []
    sick_leaves: list[VacationPeriod] = []
    unavailable_dates: list[date] = []
    preferred_shift: ShiftType | None = None
    days_off_weekly: list[int] = []
    max_consecutive_working: int | None = None

    @model_validator(mode="after")
    def validate_flags(self) -> Employee:
        if not self.employee_id:
            self.employee_id = uuid5(NAMESPACE_URL, f"duty-schedule:{self.name}").hex
        if self.morning_only and self.evening_only:
            raise ValueError(
                f"Сотрудник {self.name!r}: нельзя одновременно указать morning_only и evening_only"
            )
        if self.always_on_duty and not self.on_duty:
            raise ValueError(f"Сотрудник {self.name!r}: always_on_duty требует on_duty=True")
        if self.always_on_duty and self.city != City.MOSCOW:
            raise ValueError(
                f"Сотрудник {self.name!r}: always_on_duty поддерживается только для Москвы"
            )
        if self.always_on_duty and not self.morning_only and not self.evening_only:
            raise ValueError(
                f"Сотрудник {self.name!r}: always_on_duty требует"
                " указания morning_only или evening_only"
            )
        if self.preferred_shift in (ShiftType.VACATION, ShiftType.DAY_OFF, ShiftType.SICK_LEAVE):
            raise ValueError(
                f"Сотрудник {self.name!r}: preferred_shift не может быть vacation или day_off"
            )
        if self.max_consecutive_working is not None and not 1 <= self.max_consecutive_working <= 7:
            raise ValueError(
                f"Сотрудник {self.name!r}: max_consecutive_working должен быть от 1 до 7"
            )
        for d in self.days_off_weekly:
            if not 0 <= d <= 6:
                raise ValueError(
                    f"Сотрудник {self.name!r}: days_off_weekly содержит "
                    f"недопустимый день недели {d} (0=Пн … 6=Вс)"
                )
        return self

    def is_on_vacation(self, day: date) -> bool:
        return any(v.start <= day <= v.end for v in self.vacations)

    def is_blocked(self, day: date) -> bool:
        """Сотрудник недоступен: в отпуске или заблокировал день вручную."""
        return (
            self.is_on_vacation(day) or self.is_on_sick_leave(day) or day in self.unavailable_dates
        )

    def is_on_sick_leave(self, day: date) -> bool:
        return any(period.start <= day <= period.end for period in self.sick_leaves)

    def is_day_off_weekly(self, day: date) -> bool:
        """Постоянный выходной день недели (независимо от графика)."""
        return day.weekday() in self.days_off_weekly

    def can_work_morning(self) -> bool:
        """Может работать в утреннюю смену."""
        return not self.evening_only

    def can_work_evening(self) -> bool:
        """Может работать в вечернюю смену."""
        return not self.morning_only

    def works_on_weekend(self) -> bool:
        """Гибкий график — работает по выходным; 5/2 — нет."""
        return self.schedule_type == ScheduleType.FLEXIBLE


class PinnedAssignment(BaseModel):
    """Фиксированное назначение: конкретный сотрудник на конкретный день и смену."""

    date: date
    employee_name: str
    shift: ShiftType
    working_hours: int | None = Field(default=None, ge=1, le=8)

    @model_validator(mode="after")
    def validate_shift(self) -> PinnedAssignment:
        if self.shift in (ShiftType.VACATION, ShiftType.SICK_LEAVE):
            raise ValueError("Нельзя закрепить отпуск как пин")
        if self.working_hours is not None and self.shift != ShiftType.WORKDAY:
            raise ValueError("Индивидуальные часы допускаются только для Р")
        return self


class CarryOverState(BaseModel):
    """Перенос состояния сотрудника с конца предыдущего месяца."""

    employee_name: str
    employee_id: str | None = None
    last_shift: ShiftType | None = None
    consecutive_working: int = Field(default=0, ge=0)
    consecutive_off: int = Field(default=0, ge=0)
    consecutive_same_shift: int = Field(default=0, ge=0)
    as_of: date | None = None
    source: Literal["legacy", "manual", "schedule", "xls", "new_employee"] = "legacy"
    no_previous_shifts: bool = False

    @model_validator(mode="after")
    def validate_counters(self) -> CarryOverState:
        if self.consecutive_working and self.consecutive_off:
            raise ValueError("История не может одновременно содержать рабочую серию и выходные")
        if self.consecutive_same_shift > self.consecutive_working:
            raise ValueError("Серия одной смены не может превышать рабочую серию")
        if self.no_previous_shifts and (
            self.last_shift is not None or self.consecutive_working or self.consecutive_off
        ):
            raise ValueError("Отсутствие предыдущих смен требует пустой истории")
        return self


class Config(BaseModel):
    month: int
    year: int = Field(ge=2024, le=9999)
    timezone: str = "Europe/Moscow"
    seed: int = 42
    employees: list[Employee]
    pins: list[PinnedAssignment] = []
    carry_over: list[CarryOverState] = []
    solver: Literal["greedy", "cpsat"] = "greedy"
    optimization_priority: OptimizationPriority | None = None
    production_calendar: ProductionCalendar | None = None
    norm_choices: list[NormChoice] = []
    approvals: list[RuleApproval] = []

    @model_validator(mode="after")
    def validate_month_year(self) -> Config:
        if not 1 <= self.month <= 12:
            raise ValueError("Месяц должен быть в диапазоне 1–12")
        if self.year < 2024:
            raise ValueError("Год должен быть >= 2024")
        return self

    @model_validator(mode="after")
    def validate_team_constraints(self) -> Config:
        identities = [employee.employee_id for employee in self.employees]
        if len(set(identities)) != len(identities):
            raise ValueError("Постоянный идентификатор сотрудника должен быть уникальным")
        moscow_duty = sum(1 for e in self.employees if e.city == City.MOSCOW and e.on_duty)
        khabarovsk_duty = sum(1 for e in self.employees if e.city == City.KHABAROVSK and e.on_duty)
        if moscow_duty < 4:
            raise ValueError(
                f"Недостаточно дежурных сотрудников в Москве: {moscow_duty} (минимум 4)"
            )
        if khabarovsk_duty < 2:
            raise ValueError(
                f"Недостаточно дежурных сотрудников в Хабаровске: {khabarovsk_duty} (минимум 2)"
            )
        return self


class DaySchedule(BaseModel):
    date: date
    is_holiday: bool = False
    morning: list[str] = []
    evening: list[str] = []
    night: list[str] = []
    workday: list[str] = []
    day_off: list[str] = []
    vacation: list[str] = []
    sick_leave: list[str] = []
    workday_hours: dict[str, int] = {}

    def all_assigned(self) -> list[str]:
        return self.morning + self.evening + self.night + self.workday

    def is_covered(self) -> bool:
        """Все три обязательные смены покрыты."""
        return bool(self.morning and self.evening and self.night)


class Schedule(BaseModel):
    config: Config
    days: list[DaySchedule]
    metadata: dict[str, Any] = {}
    status: Literal["draft", "ready", "diagnostic"] = "draft"
    diagnostics: list[ScheduleDiagnostic] = []
    search_status: str = "not_run"
    revision_id: str = ""
    monthly_targets: dict[str, MonthlyTarget] = {}


def collect_config_issues(config: Config) -> tuple[list[str], list[str]]:
    """Собрать бизнес-ошибки и предупреждения конфигурации.

    Возвращает:
        (errors, warnings) — списки человекочитаемых сообщений.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not config.employees:
        errors.append("Конфигурация не содержит ни одного сотрудника.")

    from collections import Counter

    name_counts = Counter(emp.name for emp in config.employees)
    duplicated = sorted(name for name, cnt in name_counts.items() if cnt > 1)
    if duplicated:
        errors.append(
            "Имена сотрудников должны быть уникальными: "
            + ", ".join(f"«{name}»" for name in duplicated)
        )

    employees_by_name = {emp.name: emp for emp in config.employees}

    pinned_seen: set[tuple[date, str]] = set()
    for pin in config.pins:
        emp = employees_by_name.get(pin.employee_name)
        if emp is None:
            errors.append(
                f"Пин {pin.date.isoformat()}: сотрудник «{pin.employee_name}» "
                "не найден в списке employees."
            )
            continue

        key = (pin.date, emp.name)
        if key in pinned_seen:
            errors.append(
                f"Пин {pin.date.isoformat()}: для сотрудника «{emp.name}» "
                "указано несколько смен в один день."
            )
        pinned_seen.add(key)

        if emp.city == City.MOSCOW and pin.shift == ShiftType.NIGHT:
            errors.append(
                f"Пин {pin.date.isoformat()}: сотрудник «{emp.name}» из Москвы "
                "не может быть назначен на ночную смену."
            )
        if emp.city == City.KHABAROVSK and pin.shift in (
            ShiftType.MORNING,
            ShiftType.EVENING,
        ):
            errors.append(
                f"Пин {pin.date.isoformat()}: сотрудник «{emp.name}» из Хабаровска "
                "не может быть назначен на утреннюю или вечернюю смену (MSK)."
            )

        if not emp.on_duty and pin.shift in (
            ShiftType.MORNING,
            ShiftType.EVENING,
            ShiftType.NIGHT,
        ):
            warnings.append(
                f"Пин {pin.date.isoformat()}: «{emp.name}» не является дежурным "
                "(on_duty=False), но закреплён на дежурную смену."
            )

    for carry in config.carry_over:
        if carry.employee_name not in employees_by_name:
            warnings.append(
                "carry_over: состояние для сотрудника "
                f"«{carry.employee_name}» будет проигнорировано, "
                "так как такого сотрудника нет в employees."
            )

    return errors, warnings
