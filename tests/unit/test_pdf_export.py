from __future__ import annotations

from datetime import date

import pytest

from duty_schedule.models import (
    City,
    Config,
    DaySchedule,
    Employee,
    Schedule,
    ScheduleType,
)

try:
    from weasyprint import HTML  # noqa: F401

    _HAS_WEASYPRINT = True
except OSError:
    _HAS_WEASYPRINT = False

pytestmark = pytest.mark.skipif(not _HAS_WEASYPRINT, reason="weasyprint system libs not available")


def _make_schedule() -> Schedule:
    emps = [
        Employee(
            name=f"M{i}",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FLEXIBLE,
            on_duty=True,
        )
        for i in range(1, 5)
    ] + [
        Employee(
            name=f"K{i}",
            city=City.KHABAROVSK,
            schedule_type=ScheduleType.FLEXIBLE,
            on_duty=True,
        )
        for i in range(1, 3)
    ]
    days = [
        DaySchedule(
            date=date(2026, 3, 2),
            morning=["M1"],
            evening=["M2"],
            night=["K1"],
            workday=["M3"],
            day_off=["M4", "K2"],
        ),
        DaySchedule(
            date=date(2026, 3, 3),
            morning=["M2"],
            evening=["M1"],
            night=["K2"],
            workday=["M4"],
            day_off=["M3", "K1"],
        ),
    ]
    config = Config(month=3, year=2026, employees=emps)
    return Schedule(config=config, days=days)


@pytest.fixture()
def schedule() -> Schedule:
    return _make_schedule()


def test_generate_pdf_returns_bytes(schedule: Schedule) -> None:
    from duty_schedule.export.pdf import generate_schedule_pdf

    pdf_bytes = generate_schedule_pdf(schedule, page_size="A4")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:5] == b"%PDF-"


def test_generate_pdf_a3(schedule: Schedule) -> None:
    from duty_schedule.export.pdf import generate_schedule_pdf

    pdf_bytes = generate_schedule_pdf(schedule, page_size="A3")
    assert pdf_bytes[:5] == b"%PDF-"


def test_generate_pdf_with_short_days(schedule: Schedule) -> None:
    from duty_schedule.export.pdf import generate_schedule_pdf

    short = {date(2026, 3, 2)}
    pdf_bytes = generate_schedule_pdf(schedule, short_days=short)
    assert pdf_bytes[:5] == b"%PDF-"
