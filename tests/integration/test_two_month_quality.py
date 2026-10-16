from datetime import UTC, date, datetime

import pytest

from duty_schedule.models import CalendarDay, CarryOverState, ProductionCalendar, Schedule
from duty_schedule.scheduler.core import generate_schedule
from duty_schedule.scheduler.validation import validate_schedule_result
from tests.ui.fixtures import journey_config, journey_days


def next_config():
    config = journey_config()
    previous = validate_schedule_result(
        Schedule(config=config, days=journey_days(config), revision_id="april")
    )
    following = config.model_copy(deep=True)
    following.month = 5
    following.pins = []
    following.production_calendar = ProductionCalendar(
        year=2026,
        month=5,
        source="fixture",
        fetched_at=datetime(2026, 4, 1, tzinfo=UTC),
        days=[
            CalendarDay(
                date=date(2026, 5, n), kind="working" if date(2026, 5, n).weekday() < 5 else "off"
            )
            for n in range(1, 32)
        ],
    )
    following.carry_over = [
        CarryOverState.model_validate(item) for item in previous.metadata["carry_over"]
    ]
    following.previous_schedule = previous
    return following


@pytest.mark.parametrize("engine", ["greedy", "cpsat"])
def test_both_engines_use_exactly_two_months(engine):
    config = next_config()
    config.solver = engine
    result = generate_schedule(config)
    assert result.metadata["quality"]["window"] == "two_months"
    assert result.metadata["quality"]["periods"] == ["2026-04", "2026-05"]
    assert result.metadata["quality"]["source_revision_id"] == "april"
    from duty_schedule.quality_history import quality_report

    assert result.metadata["quality"] == quality_report(result)


def test_changed_role_receives_only_eligible_period_weight():
    from duty_schedule.quality_history import balance_pools

    config = next_config()
    config.employees[0].morning_only = True
    pool = balance_pools(config)["evening"]
    identity = config.employees[0].employee_id
    assert pool["weights"][identity] == 136
    assert identity not in pool["current_ids"]
    assert pool["previous_counts"][identity] > 0
