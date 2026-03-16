from __future__ import annotations

from duty_schedule.scheduler.multimonth import _next_month


def test_next_month_normal() -> None:
    assert _next_month(2026, 3) == (2026, 4)


def test_next_month_december() -> None:
    assert _next_month(2026, 12) == (2027, 1)


def test_next_month_january() -> None:
    assert _next_month(2026, 1) == (2026, 2)
