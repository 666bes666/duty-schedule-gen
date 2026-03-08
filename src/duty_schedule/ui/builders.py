from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from duty_schedule.models import (
    City,
    DaySchedule,
    Employee,
    Schedule,
    ScheduleType,
    VacationPeriod,
)
from duty_schedule.ui.mappings import (
    _RU_TO_SHIFT,
    _WEEKDAY_RU,
)


def _build_employees(
    df: pd.DataFrame,
    employee_dates: dict | None = None,
) -> tuple[list[Employee], list[str]]:
    employees: list[Employee] = []
    errors: list[str] = []
    ed = employee_dates or {}

    for _, row in df.iterrows():
        name = str(row["Имя"]).strip()
        if not name:
            continue

        city = City.MOSCOW if row["Город"] == "Москва" else City.KHABAROVSK
        stype = ScheduleType.FLEXIBLE if row["График"] == "Гибкий" else ScheduleType.FIVE_TWO

        cfg = ed.get(name, {"vacations": [], "unavailable": []})
        vacations: list[VacationPeriod] = []
        for s, e in cfg.get("vacations", []):
            try:
                vacations.append(VacationPeriod(start=s, end=e))
            except Exception as ex:
                errors.append(f"«{name}»: {ex}")
        unavailable: list[date] = list(cfg.get("unavailable", []))

        pref_shift_ru = str(row.get("Предпочт. смена", "")).strip()
        preferred_shift = _RU_TO_SHIFT.get(pref_shift_ru) if pref_shift_ru else None

        workload_raw = row.get("Загрузка%", 100)
        try:
            workload_pct = int(str(workload_raw).strip()) if str(workload_raw).strip() else 100
            workload_pct = max(1, min(100, workload_pct))
        except (ValueError, TypeError):
            workload_pct = 100

        days_off_weekly: list[int] = cfg.get("days_off_weekly", [])

        def _parse_limit(val: Any) -> int | None:
            try:
                v = int(val)  # type: ignore[arg-type]
                return v if v > 0 else None
            except (ValueError, TypeError):
                return None

        max_morning = _parse_limit(row.get("Макс. утренних"))
        max_evening = _parse_limit(row.get("Макс. вечерних"))
        max_night = _parse_limit(row.get("Макс. ночных"))
        max_cw = _parse_limit(row.get("Макс. подряд"))
        max_consec_morning = _parse_limit(row.get("Подряд: утро"))
        max_consec_evening = _parse_limit(row.get("Подряд: вечер"))
        max_consec_workday = _parse_limit(row.get("Подряд: день"))
        group = str(row.get("Группа", "")).strip() or None

        try:
            employees.append(
                Employee(
                    name=name,
                    city=city,
                    schedule_type=stype,
                    on_duty=bool(row["Дежурный"]),
                    always_on_duty=bool(row.get("Всегда на деж.", False)),
                    morning_only=bool(row["Только утро"]),
                    evening_only=bool(row["Только вечер"]),
                    vacations=vacations,
                    unavailable_dates=unavailable,
                    preferred_shift=preferred_shift,
                    workload_pct=workload_pct,
                    days_off_weekly=days_off_weekly,
                    max_morning_shifts=max_morning,
                    max_evening_shifts=max_evening,
                    max_night_shifts=max_night,
                    max_consecutive_working=max_cw,
                    max_consecutive_morning=max_consec_morning,
                    max_consecutive_evening=max_consec_evening,
                    max_consecutive_workday=max_consec_workday,
                    group=group,
                )
            )
        except Exception as e:
            errors.append(f"«{name}»: {e}")

    return employees, errors


def _schedule_to_edit_df(schedule: Schedule) -> pd.DataFrame:
    rows = []
    for d in schedule.days:
        rows.append(
            {
                "Дата": f"{d.date.day:02d}.{d.date.month:02d} {_WEEKDAY_RU[d.date.weekday()]}",
                "Утро 08–17": ", ".join(d.morning),
                "Вечер 15–00": ", ".join(d.evening),
                "Ночь 00–08": ", ".join(d.night),
                "Рабочий день": ", ".join(d.workday),
            }
        )
    return pd.DataFrame(rows)


def _edit_df_to_schedule(df: pd.DataFrame, schedule: Schedule) -> Schedule:
    new_days = []
    for (_, row), orig_day in zip(
        df.iterrows(),
        schedule.days,
        strict=False,
    ):
        _row = row

        def _names(col: str, _r: Any = _row) -> list[str]:
            val = str(_r.get(col, "")).strip()
            return [n.strip() for n in val.split(",") if n.strip()] if val else []

        all_assigned = set(
            _names("Утро 08–17")
            + _names("Вечер 15–00")
            + _names("Ночь 00–08")
            + _names("Рабочий день")
        )
        orig_all = set(
            orig_day.morning
            + orig_day.evening
            + orig_day.night
            + orig_day.workday
            + orig_day.day_off
            + orig_day.vacation
        )
        day_off = [n for n in orig_day.day_off if n not in all_assigned]
        vacation = [n for n in orig_day.vacation if n not in all_assigned]
        unassigned = [
            n for n in orig_all if n not in all_assigned and n not in day_off and n not in vacation
        ]
        day_off.extend(unassigned)

        new_days.append(
            DaySchedule(
                date=orig_day.date,
                is_holiday=orig_day.is_holiday,
                morning=_names("Утро 08–17"),
                evening=_names("Вечер 15–00"),
                night=_names("Ночь 00–08"),
                workday=_names("Рабочий день"),
                day_off=day_off,
                vacation=vacation,
            )
        )

    meta = dict(schedule.metadata)
    meta["total_mornings"] = sum(len(d.morning) for d in new_days)
    meta["total_evenings"] = sum(len(d.evening) for d in new_days)
    meta["total_nights"] = sum(len(d.night) for d in new_days)
    return Schedule.model_construct(config=schedule.config, days=new_days, metadata=meta)


def _validate_config(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    active = [row for _, row in df.iterrows() if str(row["Имя"]).strip()]
    if not active:
        errors.append("Добавьте хотя бы одного сотрудника.")
        return errors, warnings

    moscow_duty = [r for r in active if r["Город"] == "Москва" and bool(r.get("Дежурный", True))]
    khab_duty = [r for r in active if r["Город"] == "Хабаровск" and bool(r.get("Дежурный", True))]

    if len(moscow_duty) < 4:
        errors.append(f"Москва: {len(moscow_duty)} дежурных, нужно минимум 4.")
    if len(khab_duty) < 2:
        errors.append(f"Хабаровск: {len(khab_duty)} дежурных, нужно минимум 2.")

    for r in active:
        name = str(r["Имя"]).strip()
        if bool(r.get("Только утро")) and bool(r.get("Только вечер")):
            errors.append(f"«{name}»: нельзя одновременно «Только утро» и «Только вечер».")
        if bool(r.get("Всегда на деж.", False)):
            if not bool(r.get("Дежурный", True)):
                errors.append(f"«{name}»: «Всегда на деж.» требует включённого «Деж.».")
            if str(r.get("Город", "")) != "Москва":
                errors.append(f"«{name}»: «Всегда на деж.» поддерживается только для Москвы.")
            if not bool(r.get("Только утро")) and not bool(r.get("Только вечер")):
                errors.append(f"«{name}»: «Всегда на деж.» требует указания «Утро▲» или «Вечер▲».")

    return errors, warnings
