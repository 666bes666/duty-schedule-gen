from __future__ import annotations

from datetime import date

from duty_schedule.models import (
    City,
    Config,
    DaySchedule,
    Employee,
    ScheduleType,
)
from duty_schedule.scheduler.changelog import ChangeLog
from duty_schedule.scheduler.core import EmployeeState, generate_schedule
from duty_schedule.scheduler.postprocess.pipeline import (
    BalanceEveningShifts,
    Pipeline,
    PipelineContext,
    PostProcessStage,
    RecalcTotalWorking,
    build_default_pipeline,
)


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


class TestPipelineProtocol:
    def test_stage_protocol(self):
        stage = BalanceEveningShifts()
        assert isinstance(stage, PostProcessStage)
        assert stage.name == "balance_evening"

    def test_pipeline_runs_stages_in_order(self):
        days = [
            _day(1, morning=["A"], evening=["B"], night=["C"], workday=["D"]),
            _day(2, morning=["B"], evening=["A"], night=["C"], workday=["D"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C"), _emp("D")]
        states = {e.name: EmployeeState(total_working=2) for e in employees}
        ctx = PipelineContext(
            days=days,
            employees=employees,
            holidays=set(),
            pinned_on=set(),
            carry_over_cw={},
            carry_over_last_shift={},
            states=states,
            changelog=ChangeLog(),
        )

        pipeline = Pipeline([RecalcTotalWorking()])
        result = pipeline.run(ctx)
        assert len(result) == 2


class TestBuildDefaultPipeline:
    def test_default_pipeline_has_stages(self):
        pipeline = build_default_pipeline()
        assert len(pipeline.stages) > 10

    def test_priority_adds_stages(self):
        from duty_schedule.models import OptimizationPriority

        base = build_default_pipeline()
        iso = build_default_pipeline(OptimizationPriority.ISOLATED_WEEKENDS)
        assert len(iso.stages) > len(base.stages)

    def test_small_team_adds_stages(self):
        base = build_default_pipeline()
        small = build_default_pipeline(small_team=True)
        assert len(small.stages) > len(base.stages)


class TestPipelineEquivalence:
    def test_same_seed_produces_valid_schedule(self):
        team = [
            _emp("М1"),
            _emp("М2"),
            _emp("М3"),
            _emp("М4"),
            _emp("М5", on_duty=False),
            _emp("Х1", city=City.KHABAROVSK),
            _emp("Х2", city=City.KHABAROVSK),
        ]
        config = Config(month=4, year=2026, seed=42, employees=team)
        schedule = generate_schedule(config, set())
        assert len(schedule.days) > 0
        for d in schedule.days:
            assert d.is_covered()
