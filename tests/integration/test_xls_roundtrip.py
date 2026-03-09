from __future__ import annotations

import tempfile
from pathlib import Path

from duty_schedule.export.xls import export_xls
from duty_schedule.models import (
    City,
    Config,
    Employee,
    ScheduleType,
    ShiftType,
)
from duty_schedule.scheduler import generate_schedule
from duty_schedule.xls_import import parse_carry_over_from_xls


def _make_employees() -> list[Employee]:
    return [
        Employee(name=f"Москва {i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(1, 5)
    ] + [
        Employee(name=f"Хабаровск {i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(1, 3)
    ]


class TestGenerateExportImportGenerate:
    def test_full_roundtrip_no_violations(self):
        employees = _make_employees()
        config1 = Config(month=1, year=2025, seed=42, employees=employees)
        schedule1 = generate_schedule(config1, set())

        with tempfile.TemporaryDirectory() as tmpdir:
            xls_path = export_xls(schedule1, Path(tmpdir))
            xls_bytes = xls_path.read_bytes()

        carry_over_list = parse_carry_over_from_xls(xls_bytes)
        assert len(carry_over_list) >= 6

        config2 = Config(
            month=2,
            year=2025,
            seed=42,
            employees=employees,
            carry_over=carry_over_list,
        )
        schedule2 = generate_schedule(config2, set())

        for day in schedule2.days:
            assert day.is_covered(), f"Day {day.date} is not fully covered"

        co_map = {co.employee_name: co for co in carry_over_list}
        first_day = schedule2.days[0]
        for emp_name in first_day.morning:
            co = co_map.get(emp_name)
            if co and co.last_shift == ShiftType.EVENING:
                msg = (
                    f"{emp_name} had evening shift at end of month 1 "
                    f"but was assigned morning on first day of month 2"
                )
                raise AssertionError(msg)
