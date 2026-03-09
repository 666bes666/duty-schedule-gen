from __future__ import annotations

from datetime import date

import pytest
from icalendar import Calendar

from duty_schedule.export.ics import generate_employee_ics_bytes
from duty_schedule.models import (
    City,
    Config,
    DaySchedule,
    Employee,
    Schedule,
    ScheduleType,
)


def _emp(name: str, city: City = City.MOSCOW) -> Employee:
    return Employee(name=name, city=city, schedule_type=ScheduleType.FLEXIBLE)


_BASE_EMPS = [
    _emp("Иванов"),
    _emp("Петров"),
    _emp("Сидоров"),
    _emp("Козлов"),
    _emp("Дальнев", City.KHABAROVSK),
    _emp("Востоков", City.KHABAROVSK),
]


def _make_schedule(
    days: list[DaySchedule],
    extra_employees: list[Employee] | None = None,
) -> Schedule:
    employees = list(_BASE_EMPS)
    if extra_employees:
        employees.extend(extra_employees)
    return Schedule(
        config=Config(month=3, year=2025, seed=42, employees=employees),
        days=days,
    )


def _day(
    d: date,
    morning: list[str] | None = None,
    evening: list[str] | None = None,
    night: list[str] | None = None,
    workday: list[str] | None = None,
) -> DaySchedule:
    return DaySchedule(
        date=d,
        morning=morning or [],
        evening=evening or [],
        night=night or [],
        workday=workday or [],
        day_off=[],
        vacation=[],
    )


@pytest.fixture
def sample_schedule() -> Schedule:
    days = [
        _day(date(2025, 3, 1), morning=["Иванов"], evening=["Петров"]),
        _day(date(2025, 3, 2), morning=["Петров"], night=["Иванов"]),
        _day(date(2025, 3, 3), evening=["Иванов"], workday=["Петров"]),
    ]
    return _make_schedule(days)


class TestGenerateEmployeeIcsBytes:
    def test_valid_ical(self, sample_schedule: Schedule):
        data = generate_employee_ics_bytes(sample_schedule, "Иванов")
        cal = Calendar.from_ical(data)
        assert cal["VERSION"] == "2.0"

    def test_contains_only_target_shifts(self, sample_schedule: Schedule):
        data = generate_employee_ics_bytes(sample_schedule, "Иванов")
        cal = Calendar.from_ical(data)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 3
        uids = [str(c["UID"]) for c in events]
        for uid in uids:
            assert "Иванов" in uid
            assert "Петров" not in uid

    def test_has_categories(self, sample_schedule: Schedule):
        data = generate_employee_ics_bytes(sample_schedule, "Иванов")
        cal = Calendar.from_ical(data)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        for ev in events:
            assert "CATEGORIES" in ev

    def test_has_color(self, sample_schedule: Schedule):
        data = generate_employee_ics_bytes(sample_schedule, "Иванов")
        cal = Calendar.from_ical(data)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        for ev in events:
            assert "COLOR" in ev

    def test_calname(self, sample_schedule: Schedule):
        data = generate_employee_ics_bytes(sample_schedule, "Иванов")
        cal = Calendar.from_ical(data)
        assert "Иванов" in str(cal["X-WR-CALNAME"])

    def test_khabarovsk_timezone(self):
        days = [
            _day(date(2025, 3, 4), workday=["Дальнев"]),
        ]
        schedule = _make_schedule(days)
        data = generate_employee_ics_bytes(schedule, "Дальнев")
        cal = Calendar.from_ical(data)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1
        dt_start = events[0]["DTSTART"].dt
        assert str(dt_start.tzinfo) == "Asia/Vladivostok"
        assert dt_start.hour == 9
