from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

from duty_schedule._errors_fmt import format_validation_errors
from duty_schedule.models import City, Config, Employee, ScheduleType
from duty_schedule.ui.builders import _validate_config


def _row(
    *,
    name: str = "X",
    city: str = "Москва",
    schedule: str = "Гибкий",
    on_duty: bool = True,
    morning_only: bool = False,
    evening_only: bool = False,
    always_on_duty: bool = False,
) -> dict:
    return {
        "Имя": name,
        "Город": city,
        "График": schedule,
        "Дежурный": on_duty,
        "Только утро": morning_only,
        "Только вечер": evening_only,
        "Всегда на деж.": always_on_duty,
        "Предпочт. смена": "",
        "Макс. подряд": "",
    }


def _moscow_duty_rows(n: int) -> list[dict]:
    return [_row(name=f"M{i}") for i in range(1, n + 1)]


def _khab_duty_rows(n: int) -> list[dict]:
    return [_row(name=f"K{i}", city="Хабаровск") for i in range(1, n + 1)]


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _employee_from_row(row: dict) -> Employee:
    city = City.MOSCOW if row["Город"] == "Москва" else City.KHABAROVSK
    stype = ScheduleType.FLEXIBLE if row["График"] == "Гибкий" else ScheduleType.FIVE_TWO
    return Employee(
        name=row["Имя"],
        city=city,
        schedule_type=stype,
        on_duty=bool(row["Дежурный"]),
        always_on_duty=bool(row["Всегда на деж."]),
        morning_only=bool(row["Только утро"]),
        evening_only=bool(row["Только вечер"]),
    )


def _cli_format_for_row(row: dict) -> list[str]:
    try:
        _employee_from_row(row)
    except ValidationError as exc:
        return format_validation_errors(exc)
    return []


def _cli_format_for_config(rows: list[dict]) -> list[str]:
    employees: list[Employee] = []
    per_row_errors: list[str] = []
    for r in rows:
        try:
            employees.append(_employee_from_row(r))
        except ValidationError as exc:
            per_row_errors.extend(format_validation_errors(exc))
    if per_row_errors:
        return per_row_errors
    try:
        Config(month=3, year=2026, employees=employees)
    except ValidationError as exc:
        return format_validation_errors(exc)
    return []


class TestValidateConfigParityWithPydantic:
    def test_morning_and_evening_only_same_as_pydantic(self) -> None:
        bad = _row(name="Иванов", morning_only=True, evening_only=True)
        rows = _moscow_duty_rows(4) + _khab_duty_rows(2) + [bad]
        ui_errors, _ = _validate_config(_df(rows))
        cli_errors = _cli_format_for_row(bad)
        assert cli_errors, "Pydantic must reject morning_only+evening_only"
        for msg in cli_errors:
            assert msg in ui_errors, (
                f"UI must surface Pydantic message verbatim.\nPydantic: {msg!r}\nUI: {ui_errors!r}"
            )

    def test_always_on_duty_requires_on_duty_same_as_pydantic(self) -> None:
        bad = _row(
            name="Петров",
            on_duty=False,
            always_on_duty=True,
            morning_only=True,
        )
        rows = _moscow_duty_rows(4) + _khab_duty_rows(2) + [bad]
        ui_errors, _ = _validate_config(_df(rows))
        cli_errors = _cli_format_for_row(bad)
        assert cli_errors
        for msg in cli_errors:
            assert msg in ui_errors, (
                f"UI must surface Pydantic message verbatim.\nPydantic: {msg!r}\nUI: {ui_errors!r}"
            )

    def test_always_on_duty_moscow_only_same_as_pydantic(self) -> None:
        bad = _row(
            name="Сидоров",
            city="Хабаровск",
            always_on_duty=True,
            morning_only=True,
        )
        rows = _moscow_duty_rows(4) + _khab_duty_rows(2) + [bad]
        ui_errors, _ = _validate_config(_df(rows))
        cli_errors = _cli_format_for_row(bad)
        assert cli_errors
        for msg in cli_errors:
            assert msg in ui_errors, (
                f"UI must surface Pydantic message verbatim.\nPydantic: {msg!r}\nUI: {ui_errors!r}"
            )

    def test_moscow_duty_minimum_same_as_pydantic(self) -> None:
        rows = _moscow_duty_rows(3) + _khab_duty_rows(2)
        ui_errors, _ = _validate_config(_df(rows))
        cli_errors = _cli_format_for_config(rows)
        assert cli_errors
        for msg in cli_errors:
            assert msg in ui_errors, (
                f"UI must surface Pydantic message verbatim.\nPydantic: {msg!r}\nUI: {ui_errors!r}"
            )

    def test_khabarovsk_duty_minimum_same_as_pydantic(self) -> None:
        rows = _moscow_duty_rows(4) + _khab_duty_rows(1)
        ui_errors, _ = _validate_config(_df(rows))
        cli_errors = _cli_format_for_config(rows)
        assert cli_errors
        for msg in cli_errors:
            assert msg in ui_errors, (
                f"UI must surface Pydantic message verbatim.\nPydantic: {msg!r}\nUI: {ui_errors!r}"
            )


class TestValidateConfigHappyPath:
    def test_clean_config_no_errors(self) -> None:
        rows = _moscow_duty_rows(4) + _khab_duty_rows(2)
        errors, warnings = _validate_config(_df(rows))
        assert errors == []
        assert warnings == []

    def test_empty_df_returns_one_error(self) -> None:
        df = pd.DataFrame(
            columns=[
                "Имя",
                "Город",
                "График",
                "Дежурный",
                "Только утро",
                "Только вечер",
                "Всегда на деж.",
                "Предпочт. смена",
                "Макс. подряд",
            ]
        )
        errors, _ = _validate_config(df)
        assert errors
        assert any("сотрудника" in e.lower() for e in errors)


class TestFormatValidationErrors:
    def test_strips_value_error_prefix(self) -> None:
        try:
            Employee(
                name="X",
                city=City.MOSCOW,
                schedule_type=ScheduleType.FLEXIBLE,
                morning_only=True,
                evening_only=True,
            )
        except ValidationError as exc:
            messages = format_validation_errors(exc)
            assert messages
            for m in messages:
                assert not m.startswith("Value error,")
                assert not m.startswith("Value error, ")
        else:
            pytest.fail("Employee should have raised ValidationError")

    def test_returns_one_message_per_error(self) -> None:
        try:
            Config(month=3, year=2026, employees=[])
        except ValidationError as exc:
            messages = format_validation_errors(exc)
            assert len(messages) == len(exc.errors())
