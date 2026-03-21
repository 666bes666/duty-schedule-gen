from __future__ import annotations

from datetime import date

from duty_schedule.models import City, DaySchedule, Employee, ScheduleType
from duty_schedule.scheduler.postprocess.isolation import _equalize_isolated_off


def _emp(name: str, **kwargs: object) -> Employee:
    defaults: dict[str, object] = {
        "city": City.MOSCOW,
        "schedule_type": ScheduleType.FLEXIBLE,
        "on_duty": True,
    }
    defaults.update(kwargs)
    return Employee(name=name, **defaults)


def _day(d: int, **kwargs: object) -> DaySchedule:
    return DaySchedule(date=date(2026, 4, d), **kwargs)


class TestEqualizeCrossCity:
    def test_different_cities_equalized_independently(self):
        days = [
            _day(1, morning=["A"], evening=["B"], night=["X"], workday=["C", "Y"], day_off=["D"]),
            _day(2, morning=["B"], evening=["A"], night=["Y"], workday=["D", "X"], day_off=["C"]),
            _day(3, morning=["A"], evening=["B"], night=["X"], workday=["C", "Y"], day_off=["D"]),
            _day(4, morning=["B"], evening=["A"], night=["Y"], workday=["D", "X"], day_off=["C"]),
            _day(5, morning=["A"], evening=["B"], night=["X"], workday=["C", "Y"], day_off=["D"]),
        ]

        moscow_emps = [_emp("A"), _emp("B"), _emp("C"), _emp("D")]
        khab_emps = [
            _emp("X", city=City.KHABAROVSK),
            _emp("Y", city=City.KHABAROVSK),
        ]
        employees = moscow_emps + khab_emps

        _equalize_isolated_off(days, employees, set())

    def test_same_city_equalized(self):
        days = [
            _day(1, morning=["A"], evening=["B"], workday=["C"], day_off=["D"]),
            _day(2, morning=["B"], evening=["A"], workday=["D"], day_off=["C"]),
            _day(3, morning=["A"], evening=["B"], workday=["C"], day_off=["D"]),
            _day(4, morning=["B"], evening=["A"], workday=["D"], day_off=["C"]),
            _day(5, morning=["A"], evening=["B"], workday=["C"], day_off=["D"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C"), _emp("D")]

        _equalize_isolated_off(days, employees, set())
