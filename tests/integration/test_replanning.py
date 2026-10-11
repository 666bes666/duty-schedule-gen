import pytest

from duty_schedule.models import Schedule
from duty_schedule.scheduler.core import generate_schedule
from tests.ui.fixtures import journey_config, journey_days


@pytest.mark.parametrize("engine", ["greedy", "cpsat"])
def test_both_engines_preserve_valid_baseline_and_pins(engine):
    config = journey_config()
    config.solver = engine
    baseline = Schedule(config=config, days=journey_days(config))
    pins = config.pins.copy()
    result = generate_schedule(config, baseline=baseline)
    assert result.status == "ready"
    assert result.config.pins == pins
    assert result.metadata["repair"]["changed_cells"] == 0
