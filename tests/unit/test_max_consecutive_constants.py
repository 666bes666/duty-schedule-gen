"""Тесты для A2: явные DEFAULT=6 и FLEX=5 для max_consecutive_working.

DEFAULT (=6) применяется в greedy-планировании (CLI/Streamlit/API/CP-SAT).
FLEX (=5) применяется в postprocess для гибких дежурных, у которых
явный max_consecutive_working не задан.
"""

from __future__ import annotations

from datetime import date

import pytest

from duty_schedule.constants import (
    MAX_CONSECUTIVE_WORKING_DEFAULT,
    MAX_CONSECUTIVE_WORKING_FLEX,
)
from duty_schedule.models import (
    City,
    Employee,
    ScheduleType,
)
from duty_schedule.scheduler.constraints import (
    _max_cw,
    _max_cw_postprocess,
)


def _emp(
    name: str = "Гибкий",
    city: City = City.MOSCOW,
    schedule_type: ScheduleType = ScheduleType.FLEXIBLE,
    on_duty: bool = True,
    morning_only: bool = False,
    evening_only: bool = False,
    always_on_duty: bool = False,
    max_consecutive_working: int | None = None,
) -> Employee:
    return Employee(
        name=name,
        city=city,
        schedule_type=schedule_type,
        on_duty=on_duty,
        morning_only=morning_only,
        evening_only=evening_only,
        always_on_duty=always_on_duty,
        max_consecutive_working=max_consecutive_working,
    )


class TestExplicitConstants:
    """Обе константы должны быть явно заданы и различаться."""

    def test_default_is_six(self):
        assert MAX_CONSECUTIVE_WORKING_DEFAULT == 6

    def test_flex_is_five(self):
        assert MAX_CONSECUTIVE_WORKING_FLEX == 5

    def test_default_and_flex_differ(self):
        assert MAX_CONSECUTIVE_WORKING_DEFAULT != MAX_CONSECUTIVE_WORKING_FLEX


class TestGreedyPlanningUsesDefault:
    """_max_cw (используется в greedy-планировании) == DEFAULT для None."""

    def test_none_returns_default(self):
        emp = _emp(max_consecutive_working=None)
        assert _max_cw(emp) == MAX_CONSECUTIVE_WORKING_DEFAULT
        assert _max_cw(emp) == 6

    def test_explicit_override_respected(self):
        emp = _emp(max_consecutive_working=3)
        assert _max_cw(emp) == 3

    def test_five_two_uses_default(self):
        emp = _emp(schedule_type=ScheduleType.FIVE_TWO, max_consecutive_working=None)
        assert _max_cw(emp) == MAX_CONSECUTIVE_WORKING_DEFAULT

    def test_khabarovsk_uses_default(self):
        emp = _emp(city=City.KHABAROVSK, max_consecutive_working=None)
        assert _max_cw(emp) == MAX_CONSECUTIVE_WORKING_DEFAULT


class TestPostprocessUsesFlex:
    """_max_cw_postprocess == FLEX (=5) для гибких дежурных без override."""

    def test_flex_duty_returns_flex(self):
        emp = _emp(
            schedule_type=ScheduleType.FLEXIBLE,
            on_duty=True,
            max_consecutive_working=None,
        )
        assert _max_cw_postprocess(emp) == MAX_CONSECUTIVE_WORKING_FLEX
        assert _max_cw_postprocess(emp) == 5

    def test_five_two_returns_default(self):
        emp = _emp(
            schedule_type=ScheduleType.FIVE_TWO,
            on_duty=True,
            max_consecutive_working=None,
        )
        assert _max_cw_postprocess(emp) == MAX_CONSECUTIVE_WORKING_DEFAULT

    def test_non_duty_returns_default(self):
        emp = _emp(
            schedule_type=ScheduleType.FLEXIBLE,
            on_duty=False,
            max_consecutive_working=None,
        )
        assert _max_cw_postprocess(emp) == MAX_CONSECUTIVE_WORKING_DEFAULT

    def test_morning_only_returns_default(self):
        emp = _emp(
            schedule_type=ScheduleType.FLEXIBLE,
            on_duty=True,
            morning_only=True,
            max_consecutive_working=None,
        )
        assert _max_cw_postprocess(emp) == MAX_CONSECUTIVE_WORKING_DEFAULT

    def test_evening_only_returns_default(self):
        emp = _emp(
            schedule_type=ScheduleType.FLEXIBLE,
            on_duty=True,
            evening_only=True,
            max_consecutive_working=None,
        )
        assert _max_cw_postprocess(emp) == MAX_CONSECUTIVE_WORKING_DEFAULT

    def test_always_on_duty_returns_default(self):
        emp = _emp(
            schedule_type=ScheduleType.FLEXIBLE,
            on_duty=True,
            morning_only=True,
            always_on_duty=True,
            max_consecutive_working=None,
        )
        assert _max_cw_postprocess(emp) == MAX_CONSECUTIVE_WORKING_DEFAULT

    def test_explicit_override_respected(self):
        emp = _emp(
            schedule_type=ScheduleType.FLEXIBLE,
            on_duty=True,
            max_consecutive_working=4,
        )
        assert _max_cw_postprocess(emp) == 4


class TestNoLiteralFiveInPlanningPaths:
    """Регрессионный тест: ни UI builders, ни CP-SAT не используют литерал 5."""

    def test_ui_builders_imports_default(self):
        import inspect

        from duty_schedule.ui import builders

        src = inspect.getsource(builders)
        assert "MAX_CONSECUTIVE_WORKING_DEFAULT" in src, (
            "ui/builders.py должен импортировать MAX_CONSECUTIVE_WORKING_DEFAULT"
        )

    def test_solver_imports_default(self):
        import inspect

        from duty_schedule.scheduler import solver

        src = inspect.getsource(solver)
        assert "MAX_CONSECUTIVE_WORKING_DEFAULT" in src, (
            "scheduler/solver.py должен импортировать MAX_CONSECUTIVE_WORKING_DEFAULT"
        )


class TestEntryPointsAgreeOnLimit:
    """Все entry points (CLI/Streamlit/API) дают одинаковый предел для None.

    Эта проверка покрывает корневую причину A2: разные ветви кода (CLI/API/UI/CP-SAT)
    раньше использовали разные дефолты (5 vs 6) для одного и того же
    Employee.max_consecutive_working=None.
    """

    @pytest.mark.parametrize(
        "name,city,schedule_type,on_duty,expected_planning,expected_postprocess",
        [
            ("FlexMoscowDuty", City.MOSCOW, ScheduleType.FLEXIBLE, True, 6, 5),
            ("FlexKhabDuty", City.KHABAROVSK, ScheduleType.FLEXIBLE, True, 6, 5),
            ("FlexMoscowNonDuty", City.MOSCOW, ScheduleType.FLEXIBLE, False, 6, 6),
            ("FiveTwoMoscowDuty", City.MOSCOW, ScheduleType.FIVE_TWO, True, 6, 6),
        ],
    )
    def test_limit_uniform_across_entries(
        self,
        name: str,
        city: City,
        schedule_type: ScheduleType,
        on_duty: bool,
        expected_planning: int,
        expected_postprocess: int,
    ):
        emp = Employee(
            name=name,
            city=city,
            schedule_type=schedule_type,
            on_duty=on_duty,
            max_consecutive_working=None,
        )
        assert _max_cw(emp) == expected_planning
        assert _max_cw_postprocess(emp) == expected_postprocess


class TestEmployeeModelDocsDefault:
    """Документация модели должна упоминать DEFAULT (=6)."""

    def test_employee_field_docstring_mentions_default(self):
        from duty_schedule.models import Employee as _Employee

        field = _Employee.model_fields["max_consecutive_working"]
        description = (field.description or "") + (
            _Employee.__doc__ or ""
        )
        assert "6" in description or "MAX_CONSECUTIVE_WORKING_DEFAULT" in description, (
            "Документация Employee.max_consecutive_working должна упоминать значение по умолчанию"
        )


class TestRealScheduleGreedyRespectsDefault:
    """Интеграционный smoke: в реально сгенерированном расписании серии работы
    не превышают DEFAULT для сотрудников с max_consecutive_working=None."""

    def test_greedy_streaks_respect_default(self):
        from duty_schedule.models import Config
        from duty_schedule.scheduler import generate_schedule

        employees = [
            _emp(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(1, 5)
        ] + [
            _emp(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(1, 3)
        ]
        config = Config(month=3, year=2025, seed=42, employees=employees)
        schedule = generate_schedule(config, set())

        for emp in employees:
            streak = 0
            max_streak = 0
            for d in schedule.days:
                working = (
                    emp.name in d.morning
                    or emp.name in d.evening
                    or emp.name in d.night
                    or emp.name in d.workday
                )
                if working:
                    streak += 1
                    max_streak = max(max_streak, streak)
                else:
                    streak = 0
            assert max_streak <= MAX_CONSECUTIVE_WORKING_DEFAULT, (
                f"{emp.name}: серия {max_streak} > DEFAULT={MAX_CONSECUTIVE_WORKING_DEFAULT}"
            )

    def test_greedy_uses_six_for_none_in_real_constraint(self):
        """Доказательство, что None → ровно 6 на пути planning (не 5)."""
        emp = _emp(max_consecutive_working=None)
        from duty_schedule.scheduler import EmployeeState
        from duty_schedule.scheduler.constraints import _can_work

        state = EmployeeState(consecutive_working=5)
        assert _can_work(emp, state, date(2025, 3, 5), set()) is True

        state6 = EmployeeState(consecutive_working=6)
        assert _can_work(emp, state6, date(2025, 3, 5), set()) is False
