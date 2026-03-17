from __future__ import annotations

from datetime import date

from structlog.testing import capture_logs

from duty_schedule.logging import setup_logging
from duty_schedule.models import City, Config, Employee, ScheduleType
from duty_schedule.scheduler.core import generate_schedule


def _make_config() -> Config:
    moscow = [
        Employee(
            name=f"М{i}",
            city=City.MOSCOW,
            on_duty=True,
            schedule_type=ScheduleType.FLEXIBLE,
        )
        for i in range(1, 5)
    ]
    khab = [
        Employee(
            name=f"Х{i}",
            city=City.KHABAROVSK,
            on_duty=True,
            schedule_type=ScheduleType.FLEXIBLE,
        )
        for i in range(1, 3)
    ]
    return Config(
        year=2025,
        month=6,
        employees=moscow + khab,
        solver="greedy",
        seed=42,
    )


class TestLoggingSmoke:
    def test_key_events_present(self):
        setup_logging("DEBUG", force=True)
        config = _make_config()
        holidays = {date(2025, 6, 12)}

        with capture_logs() as cap:
            generate_schedule(config, holidays)

        events = [entry["event"] for entry in cap]
        assert "production_days_calculated" in events
        assert "scheduler_config" in events
        assert "schedule_generated" in events
        assert any(e == "postprocess_stage_done" for e in events)
