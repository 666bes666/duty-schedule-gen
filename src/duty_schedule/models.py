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

    @model_validator(mode="after")
    def validate_flags(self) -> Employee:
        if self.team_lead and self.on_duty:
            raise ValueError(f"Сотрудник {self.name!r}: тимлид не может быть дежурным")
        if self.morning_only and self.evening_only:
            raise ValueError(
                f"Сотрудник {self.name!r}: нельзя одновременно указать morning_only и evening_only"
            )
        return self

    def is_on_vacation(self, day: date) -> bool:
        return any(v.start <= day <= v.end for v in self.vacations)

    def is_blocked(self, day: date) -> bool:
        """Сотрудник недоступен: в отпуске или заблокировал день вручную."""
        return self.is_on_vacation(day) or day in self.unavailable_dates

    def can_work_morning(self) -> bool:
        """Может работать в утреннюю смену."""
        return not self.evening_only

    def can_work_evening(self) -> bool:
        """Может работать в вечернюю смену."""
        return not self.morning_only

    def works_on_weekend(self) -> bool:
        """Гибкий график — работает по выходным; 5/2 — нет."""
        return self.schedule_type == ScheduleType.FLEXIBLE


class Config(BaseModel):
    month: int
    year: int
    timezone: str = "Europe/Moscow"
    seed: int = 42
    employees: list[Employee]

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
