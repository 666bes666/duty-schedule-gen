from datetime import UTC, date, datetime

from duty_schedule.costs import compute_cost_hours
from duty_schedule.models import CalendarDay, Config, DaySchedule, ProductionCalendar, Schedule
from duty_schedule.stats import build_assignments, compute_stats


def test_working_saturday_is_not_weekend_for_stats_or_cost(full_config: Config) -> None:
    config = full_config.model_copy(deep=True, update={"year": 2026, "month": 4})
    config.production_calendar = ProductionCalendar(
        year=2026,
        month=4,
        source="fixture",
        fetched_at=datetime.now(UTC),
        days=[
            CalendarDay(
                date=date(2026, 4, d),
                kind="working" if d == 4 or date(2026, 4, d).weekday() < 5 else "off",
            )
            for d in range(1, 31)
        ],
    )
    name = config.employees[0].name
    schedule = Schedule(config=config, days=[DaySchedule(date=date(2026, 4, 4), morning=[name])])
    stat = compute_stats(schedule, build_assignments(schedule), 23)[0]
    assert stat.weekend_work == 0
    assert stat.total_hours == 8
    assert stat.selected_hours == 184
    assert compute_cost_hours(name, schedule, set()) == 8.0


def test_individual_workday_hours_used_by_stats_and_cost(full_config: Config) -> None:
    name = full_config.employees[0].name
    schedule = Schedule(
        config=full_config,
        days=[DaySchedule(date=date(2025, 3, 3), workday=[name], workday_hours={name: 3})],
    )
    stats = compute_stats(schedule, build_assignments(schedule), 21)
    assert stats[0].total_hours == 3
    assert compute_cost_hours(name, schedule, set()) == 3.0
