"""Модели данных: сотрудники, конфигурация, расписание."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, model_validator


class ScheduleType(StrEnum):
    FLEXIBLE = "flexible"
    FIVE_TWO = "5/2"


class ShiftType(StrEnum):
    MORNING = "morning"
    EVENING = "evening"
    NIGHT = "night"
    WORKDAY = "workday"
    DAY_OFF = "day_off"
    VACATION = "vacation"


class City(StrEnum):
    MOSCOW = "moscow"
    KHABAROVSK = "khabarovsk"


# Shift time bounds (MSK)
SHIFT_START = {
    ShiftType.MORNING: (8, 0),
    ShiftType.EVENING: (15, 0),
    ShiftType.NIGHT: (0, 0),
    ShiftType.WORKDAY: (9, 0),
}
SHIFT_END = {
    ShiftType.MORNING: (17, 0),
    ShiftType.EVENING: (0, 0),  # next day
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
}


class VacationPeriod(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def end_after_start(self) -> VacationPeriod:
        if self.end < self.start:
            raise ValueError("Дата окончания отпуска должна быть не раньше даты начала")
        return self


class Employee(BaseModel):
    name: str
    city: City
    schedule_type: ScheduleType
    on_duty: bool = True
    morning_only: bool = False
    evening_only: bool = False
    team_lead: bool = False
    vacations: list[VacationPeriod] = []
    unavailable_dates: list[date] = []
    # Фича 1: лимиты типов смен в месяц (None = без ограничений)
    max_morning_shifts: int | None = None
    max_evening_shifts: int | None = None
    max_night_shifts: int | None = None
    # Фича 2: предпочтительная смена (мягкий приоритет при выборе)
    preferred_shift: ShiftType | None = None
    # Фича 3: норма нагрузки в % (100 = полная ставка, 50 = 0.5 ставки)
    workload_pct: int = 100
    # Фича 4: постоянные выходные дни недели (0=Пн … 6=Вс)
    days_off_weekly: list[int] = []
    # Фича 5: индивидуальный лимит рабочих дней подряд (None = глобальный дефолт 5)
    max_consecutive_working: int | None = None
    # Фича 6: группа — не ставить двух из одной группы на одну смену в один день
    group: str | None = None
    # Фича 7: роль — отображается в XLS рядом с именем (информационно)
    role: str = ""

    @model_validator(mode="after")
    def validate_flags(self) -> Employee:
        if self.team_lead and self.on_duty:
            raise ValueError(f"Сотрудник {self.name!r}: тимлид не может быть дежурным")
        if self.morning_only and self.evening_only:
            raise ValueError(
                f"Сотрудник {self.name!r}: нельзя одновременно указать morning_only и evening_only"
            )
        if not 1 <= self.workload_pct <= 100:
            raise ValueError(
                f"Сотрудник {self.name!r}: workload_pct должен быть в диапазоне 1–100"
            )
        if self.preferred_shift in (ShiftType.VACATION, ShiftType.DAY_OFF):
            raise ValueError(
                f"Сотрудник {self.name!r}: preferred_shift не может быть vacation или day_off"
            )
        if self.max_consecutive_working is not None and self.max_consecutive_working < 1:
            raise ValueError(
                f"Сотрудник {self.name!r}: max_consecutive_working должен быть >= 1"
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
        return self.is_on_vacation(day) or day in self.unavailable_dates

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

    @model_validator(mode="after")
    def validate_shift(self) -> PinnedAssignment:
        if self.shift == ShiftType.VACATION:
            raise ValueError("Нельзя закрепить отпуск как пин")
        return self


class CarryOverState(BaseModel):
    """Перенос состояния сотрудника с конца предыдущего месяца."""
    employee_name: str
    last_shift: ShiftType | None = None
    consecutive_working: int = 0
    consecutive_off: int = 0


class Config(BaseModel):
    month: int
    year: int
    timezone: str = "Europe/Moscow"
    seed: int = 42
    employees: list[Employee]
    pins: list[PinnedAssignment] = []
    carry_over: list[CarryOverState] = []

    @model_validator(mode="after")
    def validate_month_year(self) -> Config:
        if not 1 <= self.month <= 12:
            raise ValueError("Месяц должен быть в диапазоне 1–12")
        if self.year < 2024:
            raise ValueError("Год должен быть >= 2024")
        return self

    @model_validator(mode="after")
    def validate_team_constraints(self) -> Config:
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

    def all_assigned(self) -> list[str]:
        return self.morning + self.evening + self.night + self.workday

    def is_covered(self) -> bool:
        """Все три обязательные смены покрыты."""
        return bool(self.morning and self.evening and self.night)


class Schedule(BaseModel):
    config: Config
    days: list[DaySchedule]
    metadata: dict[str, Any] = {}


def collect_config_issues(config: Config) -> tuple[list[str], list[str]]:
    """Собрать бизнес-ошибки и предупреждения конфигурации.

    Возвращает:
        (errors, warnings) — списки человекочитаемых сообщений.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Базовые проверки поверх pydantic-валидации
    if not config.employees:
        errors.append("Конфигурация не содержит ни одного сотрудника.")

    # Уникальность имён сотрудников
    from collections import Counter

    name_counts = Counter(emp.name for emp in config.employees)
    duplicated = sorted(name for name, cnt in name_counts.items() if cnt > 1)
    if duplicated:
        errors.append(
            "Имена сотрудников должны быть уникальными: "
            + ", ".join(f"«{name}»" for name in duplicated)
        )

    employees_by_name = {emp.name: emp for emp in config.employees}

    # Валидация пинов (фиксированных назначений)
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

        # Городские ограничения для типов смен
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

        # Информационные предупреждения о нетипичных комбинациях
        if not emp.on_duty and pin.shift in (
            ShiftType.MORNING,
            ShiftType.EVENING,
            ShiftType.NIGHT,
        ):
            warnings.append(
                f"Пин {pin.date.isoformat()}: «{emp.name}» не является дежурным "
                "(on_duty=False), но закреплён на дежурную смену."
            )
        if emp.team_lead and pin.shift in (
            ShiftType.MORNING,
            ShiftType.EVENING,
            ShiftType.NIGHT,
        ):
            warnings.append(
                f"Пин {pin.date.isoformat()}: тимлид «{emp.name}» закреплён "
                "на дежурную смену."
            )

    # Переносимые состояния для отсутствующих сотрудников
    for carry in config.carry_over:
        if carry.employee_name not in employees_by_name:
            warnings.append(
                "carry_over: состояние для сотрудника "
                f"«{carry.employee_name}» будет проигнорировано, "
                "так как такого сотрудника нет в employees."
            )

    return errors, warnings
