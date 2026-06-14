from __future__ import annotations

from datetime import date

import pytest

from duty_schedule.models import (
    CarryOverState,
    City,
    Config,
    Employee,
    PinnedAssignment,
    ScheduleType,
    ShiftType,
    collect_config_issues,
)
from tests.contract.conftest import JSON_HEADERS, patch_schedule_holidays


def _base_employees() -> list[Employee]:
    return [
        Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(4)
    ] + [
        Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(2)
    ]


def _config_duplicate_pin() -> Config:
    return Config(
        month=3,
        year=2025,
        employees=_base_employees(),
        pins=[
            PinnedAssignment(
                date=date(2025, 3, 1),
                employee_name="М0",
                shift=ShiftType.MORNING,
            ),
            PinnedAssignment(
                date=date(2025, 3, 1),
                employee_name="М0",
                shift=ShiftType.EVENING,
            ),
        ],
    )


def _config_pin_unknown_employee() -> Config:
    return Config(
        month=3,
        year=2025,
        employees=_base_employees(),
        pins=[
            PinnedAssignment(
                date=date(2025, 3, 1),
                employee_name="НеСуществует",
                shift=ShiftType.MORNING,
            ),
        ],
    )


def _config_duplicate_employee_names() -> Config:
    emps = _base_employees()
    emps.append(Employee(name="М0", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE))
    return Config(month=3, year=2025, employees=emps)


def _config_carry_over_unknown_employee() -> Config:
    return Config(
        month=3,
        year=2025,
        employees=_base_employees(),
        carry_over=[CarryOverState(employee_name="Неизвестный", consecutive_working=3)],
    )


class TestApiStrictValidationContract:
    @pytest.mark.asyncio
    async def test_duplicate_pin_returns_400(self, client) -> None:
        config = _config_duplicate_pin()
        cli_errors, _ = collect_config_issues(config)
        assert cli_errors, "fixture must trigger CLI errors"

        with patch_schedule_holidays():
            resp = await client.post(
                "/api/v1/schedule/generate",
                content=config.model_dump_json(),
                headers=JSON_HEADERS,
            )

        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"] == cli_errors

    @pytest.mark.asyncio
    async def test_pin_for_unknown_employee_returns_400(self, client) -> None:
        config = _config_pin_unknown_employee()
        cli_errors, _ = collect_config_issues(config)
        assert cli_errors, "fixture must trigger CLI errors"

        with patch_schedule_holidays():
            resp = await client.post(
                "/api/v1/schedule/generate",
                content=config.model_dump_json(),
                headers=JSON_HEADERS,
            )

        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"] == cli_errors

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "config_factory",
        [
            _config_duplicate_pin,
            _config_pin_unknown_employee,
            _config_duplicate_employee_names,
        ],
        ids=["duplicate_pin", "pin_unknown_employee", "duplicate_employee_names"],
    )
    async def test_collect_config_issues_parity(self, client, config_factory) -> None:
        config = config_factory()
        cli_errors, _ = collect_config_issues(config)
        assert cli_errors, "fixture must produce errors via collect_config_issues"

        with patch_schedule_holidays():
            resp = await client.post(
                "/api/v1/schedule/generate",
                content=config.model_dump_json(),
                headers=JSON_HEADERS,
            )

        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"] == cli_errors

    @pytest.mark.asyncio
    async def test_carry_over_unknown_employee_not_rejected(self, client) -> None:
        config = _config_carry_over_unknown_employee()
        cli_errors, cli_warnings = collect_config_issues(config)
        assert cli_errors == []
        assert cli_warnings, "fixture must produce a CLI warning"

        with patch_schedule_holidays():
            resp = await client.post(
                "/api/v1/schedule/generate",
                content=config.model_dump_json(),
                headers=JSON_HEADERS,
            )

        assert resp.status_code != 400
