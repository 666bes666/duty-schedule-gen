from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from duty_schedule.api.schemas import EmployeeStatsSchema
from duty_schedule.api.whatif_service import (
    apply_patch,
    compute_deltas,
    compute_summary,
    run_whatif,
)
from duty_schedule.models import City, Config, Employee, ScheduleType
from duty_schedule.stats import EmployeeStats


def _emp(
    name: str,
    city: City = City.MOSCOW,
    schedule_type: ScheduleType = ScheduleType.FLEXIBLE,
) -> Employee:
    return Employee(name=name, city=city, schedule_type=schedule_type)


def _make_config(seed: int = 42) -> Config:
    return Config(
        month=3,
        year=2025,
        seed=seed,
        employees=[
            _emp("Иванов Иван"),
            _emp("Петров Пётр"),
            _emp("Сидоров Сидор"),
            _emp("Козлов Коля"),
            _emp("Дальнев Дмитрий", City.KHABAROVSK),
            _emp("Востоков Виктор", City.KHABAROVSK),
        ],
    )


HOLIDAYS: set[date] = {date(2025, 3, 8), date(2025, 3, 10)}
SHORT_DAYS: set[date] = {date(2025, 3, 7)}


class TestApplyPatch:
    def test_change_seed(self) -> None:
        cfg = _make_config(seed=42)
        patched = apply_patch(cfg, {"seed": 99})
        assert patched.seed == 99
        assert patched.month == cfg.month
        assert patched.year == cfg.year
        assert len(patched.employees) == len(cfg.employees)

    def test_replace_employees(self) -> None:
        cfg = _make_config()
        new_employees = [
            _emp("А Андрей").model_dump(),
            _emp("Б Борис").model_dump(),
            _emp("В Виктор").model_dump(),
            _emp("Г Геннадий").model_dump(),
            _emp("Д Дмитрий", City.KHABAROVSK).model_dump(),
            _emp("Е Евгений", City.KHABAROVSK).model_dump(),
        ]
        patched = apply_patch(cfg, {"employees": new_employees})
        assert patched.employees[0].name == "А Андрей"

    def test_rejects_month_in_patch(self) -> None:
        from duty_schedule.api.schemas import VariantPatch

        with pytest.raises(ValidationError, match="month"):
            VariantPatch(name="bad", patch={"month": 4})

    def test_rejects_year_in_patch(self) -> None:
        from duty_schedule.api.schemas import VariantPatch

        with pytest.raises(ValidationError, match="year"):
            VariantPatch(name="bad", patch={"year": 2026})

    def test_invalid_employee_raises(self) -> None:
        cfg = _make_config()
        with pytest.raises(ValidationError):
            apply_patch(cfg, {"employees": [{"name": "X"}]})

    def test_preserves_unchanged_fields(self) -> None:
        cfg = _make_config()
        cfg_with_tz = Config(
            month=3,
            year=2025,
            seed=42,
            timezone="Asia/Vladivostok",
            employees=cfg.employees,
        )
        patched = apply_patch(cfg_with_tz, {"seed": 99})
        assert patched.timezone == "Asia/Vladivostok"


class TestComputeSummary:
    def _make_stats(
        self,
        names: list[str],
        total_working: list[int],
        targets: list[int],
        isolated_off: list[int] | None = None,
        weekend_work: list[int] | None = None,
    ) -> list[EmployeeStats]:
        _isolated = isolated_off or [0] * len(names)
        _weekend = weekend_work or [0] * len(names)
        return [
            EmployeeStats(
                name=n,
                city="Москва",
                total_working=tw,
                target=t,
                morning=tw // 2,
                evening=tw - tw // 2,
                night=0,
                workday=0,
                day_off=31 - tw,
                vacation=0,
                weekend_work=ww,
                holiday_work=0,
                max_streak_work=5,
                max_streak_rest=2,
                isolated_off=iso,
                paired_off=0,
                total_hours=tw * 8,
            )
            for n, tw, t, iso, ww in zip(
                names,
                total_working,
                targets,
                _isolated,
                _weekend,
                strict=True,
            )
        ]

    def test_perfect_schedule(self) -> None:
        from duty_schedule.models import DaySchedule, Schedule

        stats = self._make_stats(
            ["A", "B"],
            [20, 20],
            [20, 20],
        )
        days = [
            DaySchedule(
                date=date(2025, 3, d),
                morning=["A"],
                evening=["B"],
                night=["X"],
            )
            for d in range(1, 32)
        ]
        cfg = _make_config()
        schedule = Schedule(config=cfg, days=days)
        summary = compute_summary(stats, schedule)
        assert summary.fairness_score == 0.0
        assert summary.workload_stddev == 0.0

    def test_unbalanced_schedule(self) -> None:
        from duty_schedule.models import DaySchedule, Schedule

        stats = self._make_stats(
            ["A", "B"],
            [25, 15],
            [20, 20],
            isolated_off=[3, 1],
            weekend_work=[8, 2],
        )
        days = [
            DaySchedule(
                date=date(2025, 3, d),
                morning=["A"],
                evening=["B"],
                night=["X"],
            )
            for d in range(1, 32)
        ]
        cfg = _make_config()
        schedule = Schedule(config=cfg, days=days)
        summary = compute_summary(stats, schedule)
        assert summary.fairness_score > 0
        assert summary.workload_stddev > 0
        assert summary.isolated_off_total == 4
        assert summary.weekend_balance_stddev > 0


class TestComputeDeltas:
    def _stat(
        self,
        name: str,
        total_working: int = 20,
        target: int = 20,
        **kw: int,
    ) -> EmployeeStatsSchema:
        defaults = {
            "city": "Москва",
            "total_working": total_working,
            "target": target,
            "morning": 10,
            "evening": 10,
            "night": 0,
            "workday": 0,
            "day_off": 11,
            "vacation": 0,
            "weekend_work": 4,
            "holiday_work": 0,
            "max_streak_work": 5,
            "max_streak_rest": 2,
            "isolated_off": 2,
            "paired_off": 3,
            "total_hours": total_working * 8,
        }
        defaults.update(kw)
        return EmployeeStatsSchema(name=name, **defaults)

    def test_correct_deltas_and_direction(self) -> None:
        b = [self._stat("A", isolated_off=3, paired_off=2)]
        v = [self._stat("A", isolated_off=1, paired_off=4)]
        deltas = compute_deltas(b, v)
        assert len(deltas) == 1
        d = deltas[0]
        assert d.name == "A"
        assert d.metrics["isolated_off"].delta == -2
        assert d.metrics["isolated_off"].direction == "improved"
        assert d.metrics["paired_off"].delta == 2
        assert d.metrics["paired_off"].direction == "improved"

    def test_intersection_of_employees(self) -> None:
        b = [self._stat("A"), self._stat("B")]
        v = [self._stat("B"), self._stat("C")]
        deltas = compute_deltas(b, v)
        names = [d.name for d in deltas]
        assert names == ["B"]

    def test_zero_deltas_unchanged(self) -> None:
        b = [self._stat("A")]
        v = [self._stat("A")]
        deltas = compute_deltas(b, v)
        for metric in deltas[0].metrics.values():
            assert metric.delta == 0
            assert metric.direction == "unchanged"

    def test_total_working_vs_target(self) -> None:
        b = [self._stat("A", total_working=22, target=20)]
        v = [self._stat("A", total_working=21, target=20)]
        deltas = compute_deltas(b, v)
        d = deltas[0].metrics["total_working"]
        assert d.direction == "improved"

    def test_max_streak_work_lower_is_better(self) -> None:
        b = [self._stat("A", max_streak_work=6)]
        v = [self._stat("A", max_streak_work=4)]
        deltas = compute_deltas(b, v)
        d = deltas[0].metrics["max_streak_work"]
        assert d.direction == "improved"
        assert d.delta == -2


class TestRunWhatif:
    def test_single_variant_success(self) -> None:
        cfg = _make_config(seed=42)
        result = run_whatif(
            cfg,
            [("seed=99", {"seed": 99})],
            HOLIDAYS,
            SHORT_DAYS,
        )
        assert len(result.baseline.stats) == 6
        assert len(result.variants) == 1
        v = result.variants[0]
        assert v.status == "success"
        assert v.stats is not None
        assert v.deltas is not None
        assert v.summary is not None

    def test_partial_failure(self) -> None:
        cfg = _make_config(seed=42)
        bad_employees = [_emp("Один Один").model_dump()]
        result = run_whatif(
            cfg,
            [
                ("good", {"seed": 99}),
                ("bad", {"employees": bad_employees}),
            ],
            HOLIDAYS,
            SHORT_DAYS,
        )
        statuses = {v.name: v.status for v in result.variants}
        assert statuses["good"] == "success"
        assert statuses["bad"] == "error"
        assert result.variants[1].error is not None
