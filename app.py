"""Streamlit-интерфейс генератора графика дежурств."""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from duty_schedule.calendar import CalendarError, fetch_holidays
from duty_schedule.models import CarryOverState, City, Config, Employee, PinnedAssignment, ScheduleType, ShiftType, VacationPeriod
from duty_schedule.scheduler import ScheduleError, generate_schedule
from duty_schedule.export.xls import export_xls

# ── Константы ────────────────────────────────────────────────────────────────

MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
_WEEKDAY_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

_CITY_TO_RU   = {"moscow": "Москва", "khabarovsk": "Хабаровск"}
_RU_TO_CITY   = {"Москва": "moscow", "Хабаровск": "khabarovsk"}
_STYPE_TO_RU  = {"flexible": "Гибкий", "5/2": "5/2"}
_RU_TO_STYPE  = {"Гибкий": "flexible", "5/2": "5/2"}

_EMPTY_ROW = {
    "Имя": "",
    "Город": "Москва",
    "График": "Гибкий",
    "Дежурный": True,
    "Только утро": False,
    "Только вечер": False,
    "Тимлид": False,
    "Отпуск": "",
    "Недоступен": "",      # фича 2 (разовые блокировки), зарезервировано
}

_DEFAULT_ROWS = [
    {**_EMPTY_ROW, "Город": "Москва"},
    {**_EMPTY_ROW, "Город": "Москва"},
    {**_EMPTY_ROW, "Город": "Москва"},
    {**_EMPTY_ROW, "Город": "Москва"},
    {**_EMPTY_ROW, "Город": "Хабаровск"},
    {**_EMPTY_ROW, "Город": "Хабаровск"},
]

_TABLE_KEY_PREFIX = "employees_table"

_SHIFTS_RU = ["Утро", "Вечер", "Ночь", "Рабочий день", "Выходной"]
_RU_TO_SHIFT = {
    "Утро":        ShiftType.MORNING,
    "Вечер":       ShiftType.EVENING,
    "Ночь":        ShiftType.NIGHT,
    "Рабочий день": ShiftType.WORKDAY,
    "Выходной":    ShiftType.DAY_OFF,
}
_SHIFT_TO_RU = {v: k for k, v in _RU_TO_SHIFT.items()}

_EMPTY_PIN_ROW = {"Дата": "", "Сотрудник": "", "Смена": "Утро"}


# ── Session state ─────────────────────────────────────────────────────────────

def _init_state() -> None:
    if "table_version" not in st.session_state:
        st.session_state["table_version"] = 0
    if "employees_df" not in st.session_state:
        st.session_state["employees_df"] = pd.DataFrame(_DEFAULT_ROWS)
    if "cfg_month" not in st.session_state:
        st.session_state["cfg_month"] = date.today().month
    if "cfg_year" not in st.session_state:
        st.session_state["cfg_year"] = date.today().year
    if "cfg_seed" not in st.session_state:
        st.session_state["cfg_seed"] = 42
    if "pins_df" not in st.session_state:
        st.session_state["pins_df"] = pd.DataFrame([_EMPTY_PIN_ROW])
    if "carry_over" not in st.session_state:
        st.session_state["carry_over"] = []


def _bump_table() -> None:
    """Увеличить версию ключа таблицы, чтобы data_editor пересоздался с новыми данными."""
    st.session_state["table_version"] += 1


# ── Парсинг/сериализация ──────────────────────────────────────────────────────

def _parse_vacations(
    text: str, year: int, emp_name: str,
) -> tuple[list[VacationPeriod], str | None]:
    """Распарсить отпуска из строки «дд.мм–дд.мм, дд.мм–дд.мм»."""
    if not text.strip():
        return [], None
    periods: list[VacationPeriod] = []
    for raw in text.replace("–", "-").split(","):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split("-", 1)
        if len(parts) != 2:
            return [], f"«{emp_name}»: неверный формат отпуска «{raw}» (нужно дд.мм–дд.мм)"
        try:
            start = datetime.strptime(f"{parts[0].strip()}.{year}", "%d.%m.%Y").date()
            end   = datetime.strptime(f"{parts[1].strip()}.{year}", "%d.%m.%Y").date()
        except ValueError:
            return [], f"«{emp_name}»: не удалось разобрать дату «{raw}»"
        periods.append(VacationPeriod(start=start, end=end))
    return periods, None


def _vacations_to_str(vacations: list[dict], year: int) -> str:
    """Преобразовать список {start, end} из YAML в строку «дд.мм–дд.мм»."""
    parts = []
    for v in vacations:
        s = date.fromisoformat(str(v["start"]))
        e = date.fromisoformat(str(v["end"]))
        # показываем только если в том же году
        if s.year == year and e.year == year:
            parts.append(f"{s.day:02d}.{s.month:02d}–{e.day:02d}.{e.month:02d}")
    return ", ".join(parts)


def _df_to_yaml(
    df: pd.DataFrame, month: int, year: int, seed: int,
    pins_df: pd.DataFrame | None = None,
    carry_over: list[dict] | None = None,
) -> str:
    """Сериализовать таблицу сотрудников в YAML (совместимый с CLI)."""
    employees = []
    for _, row in df.iterrows():
        name = str(row["Имя"]).strip()
        if not name:
            continue
        vacations: list[dict] = []
        vac_text = str(row.get("Отпуск", "")).strip()
        for raw in vac_text.replace("–", "-").split(","):
            raw = raw.strip()
            if not raw:
                continue
            parts = raw.split("-", 1)
            if len(parts) == 2:
                try:
                    s = datetime.strptime(f"{parts[0].strip()}.{year}", "%d.%m.%Y").date()
                    e = datetime.strptime(f"{parts[1].strip()}.{year}", "%d.%m.%Y").date()
                    vacations.append({"start": s.isoformat(), "end": e.isoformat()})
                except ValueError:
                    pass
        unavailable_dates: list[str] = []
        unavail_text = str(row.get("Недоступен", "")).strip()
        for raw in unavail_text.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = datetime.strptime(f"{raw}.{year}", "%d.%m.%Y").date()
                unavailable_dates.append(d.isoformat())
            except ValueError:
                pass
        emp: dict = {
            "name": name,
            "city": _RU_TO_CITY.get(str(row["Город"]), "moscow"),
            "schedule_type": _RU_TO_STYPE.get(str(row["График"]), "flexible"),
            "on_duty": bool(row["Дежурный"]),
            "morning_only": bool(row["Только утро"]),
            "evening_only": bool(row["Только вечер"]),
            "team_lead": bool(row["Тимлид"]),
        }
        if vacations:
            emp["vacations"] = vacations
        if unavailable_dates:
            emp["unavailable_dates"] = unavailable_dates
        employees.append(emp)

    config_dict: dict = {
        "month": int(month),
        "year": int(year),
        "seed": int(seed),
        "employees": employees,
    }
    if pins_df is not None:
        pins_list = _pins_df_to_list(pins_df, year)
        if pins_list:
            config_dict["pins"] = pins_list
    if carry_over:
        config_dict["carry_over"] = carry_over
    return yaml.dump(config_dict, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _pins_df_to_list(pins_df: pd.DataFrame, year: int) -> list[dict]:
    """Сериализовать таблицу пинов в список dict для YAML."""
    result = []
    for _, row in pins_df.iterrows():
        date_str = str(row.get("Дата", "")).strip()
        emp_name = str(row.get("Сотрудник", "")).strip()
        shift_ru = str(row.get("Смена", "")).strip()
        if not date_str or not emp_name or not shift_ru:
            continue
        try:
            d = datetime.strptime(f"{date_str}.{year}", "%d.%m.%Y").date()
        except ValueError:
            continue
        shift = _RU_TO_SHIFT.get(shift_ru)
        if shift is None:
            continue
        result.append({"date": d.isoformat(), "employee_name": emp_name, "shift": str(shift)})
    return result


def _pins_list_to_df(pins: list[dict], year: int) -> pd.DataFrame:
    """Десериализовать список пинов из YAML в DataFrame."""
    rows = []
    for p in pins:
        try:
            d = date.fromisoformat(str(p["date"]))
        except (ValueError, KeyError):
            continue
        if d.year != year:
            continue
        shift_str = str(p.get("shift", ""))
        shift_ru = _SHIFT_TO_RU.get(ShiftType(shift_str), "Утро") if shift_str else "Утро"
        rows.append({
            "Дата":       f"{d.day:02d}.{d.month:02d}",
            "Сотрудник":  str(p.get("employee_name", "")),
            "Смена":      shift_ru,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame([_EMPTY_PIN_ROW])


def _yaml_to_df(
    raw_yaml: str, year: int,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, list[dict], int, int, int, str | None]:
    """Загрузить YAML конфиг → (employees_df, pins_df, carry_over, month, year, seed, error)."""
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as e:
        return None, None, [], 0, 0, 42, f"Ошибка разбора YAML: {e}"

    if not isinstance(data, dict):
        return None, None, [], 0, 0, 42, "Неверный формат файла конфигурации."

    month = int(data.get("month", date.today().month))
    year_val = int(data.get("year", year))
    seed = int(data.get("seed", 42))
    rows = []
    for emp in data.get("employees", []):
        vac_str = _vacations_to_str(emp.get("vacations", []), year_val)
        unavail_dates = emp.get("unavailable_dates", [])
        unavail_str = ", ".join(
            f"{date.fromisoformat(str(d)).day:02d}.{date.fromisoformat(str(d)).month:02d}"
            for d in unavail_dates
            if date.fromisoformat(str(d)).year == year_val
        )
        rows.append({
            "Имя":          emp.get("name", ""),
            "Город":        _CITY_TO_RU.get(emp.get("city", "moscow"), "Москва"),
            "График":       _STYPE_TO_RU.get(emp.get("schedule_type", "flexible"), "Гибкий"),
            "Дежурный":     bool(emp.get("on_duty", True)),
            "Только утро":  bool(emp.get("morning_only", False)),
            "Только вечер": bool(emp.get("evening_only", False)),
            "Тимлид":       bool(emp.get("team_lead", False)),
            "Отпуск":       vac_str,
            "Недоступен":   unavail_str,
        })

    if not rows:
        rows = _DEFAULT_ROWS.copy()

    pins_df = _pins_list_to_df(data.get("pins", []), year_val)
    carry_over = data.get("carry_over", [])
    return pd.DataFrame(rows), pins_df, carry_over, month, year_val, seed, None


def _parse_unavailable(
    text: str, year: int, emp_name: str,
) -> tuple[list[date], str | None]:
    """Распарсить разовые недоступные дни из строки «дд.мм, дд.мм»."""
    if not text.strip():
        return [], None
    result: list[date] = []
    for raw in text.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = datetime.strptime(f"{raw}.{year}", "%d.%m.%Y").date()
        except ValueError:
            return [], f"«{emp_name}»: неверный формат недоступного дня «{raw}» (нужно дд.мм)"
        result.append(d)
    return result, None


def _build_employees(df: pd.DataFrame, year: int) -> tuple[list[Employee], list[str]]:
    """DataFrame → список Employee."""
    employees: list[Employee] = []
    errors: list[str] = []
    for _, row in df.iterrows():
        name = str(row["Имя"]).strip()
        if not name:
            continue
        city  = City.MOSCOW if row["Город"] == "Москва" else City.KHABAROVSK
        stype = ScheduleType.FLEXIBLE if row["График"] == "Гибкий" else ScheduleType.FIVE_TWO
        vacations, err = _parse_vacations(str(row.get("Отпуск", "")), year, name)
        if err:
            errors.append(err)
            continue
        unavailable, err2 = _parse_unavailable(str(row.get("Недоступен", "")), year, name)
        if err2:
            errors.append(err2)
            continue
        try:
            employees.append(Employee(
                name=name, city=city, schedule_type=stype,
                on_duty=bool(row["Дежурный"]),
                morning_only=bool(row["Только утро"]),
                evening_only=bool(row["Только вечер"]),
                team_lead=bool(row["Тимлид"]),
                vacations=vacations,
                unavailable_dates=unavailable,
            ))
        except Exception as e:
            errors.append(f"«{name}»: {e}")
    return employees, errors


# ── Конвертация расписания ↔ DataFrame ────────────────────────────────────────

def _schedule_to_edit_df(schedule: "Schedule") -> pd.DataFrame:
    """Преобразовать Schedule в редактируемый DataFrame (строки = дни)."""
    rows = []
    for d in schedule.days:
        rows.append({
            "Дата":         f"{d.date.day:02d}.{d.date.month:02d} {_WEEKDAY_RU[d.date.weekday()]}",
            "Утро 08–17":   ", ".join(d.morning),
            "Вечер 15–00":  ", ".join(d.evening),
            "Ночь 00–08":   ", ".join(d.night),
            "Рабочий день": ", ".join(d.workday),
        })
    return pd.DataFrame(rows)


def _edit_df_to_schedule(df: pd.DataFrame, schedule: "Schedule") -> "Schedule":
    """Пересобрать Schedule из отредактированного DataFrame."""
    from duty_schedule.models import DaySchedule, Schedule as ScheduleModel

    new_days = []
    for (_, row), orig_day in zip(df.iterrows(), schedule.days):
        def _names(col: str) -> list[str]:
            val = str(row.get(col, "")).strip()
            return [n.strip() for n in val.split(",") if n.strip()] if val else []

        # vacation и day_off вычисляем из оригинала минус то, что переехало в другие смены
        all_assigned = set(_names("Утро 08–17") + _names("Вечер 15–00") + _names("Ночь 00–08") + _names("Рабочий день"))
        orig_all = set(orig_day.morning + orig_day.evening + orig_day.night + orig_day.workday + orig_day.day_off + orig_day.vacation)
        day_off = [n for n in orig_day.day_off if n not in all_assigned]
        vacation = [n for n in orig_day.vacation if n not in all_assigned]
        # Employees not in any shift → day_off
        unassigned = [n for n in orig_all if n not in all_assigned and n not in day_off and n not in vacation]
        day_off.extend(unassigned)

        new_days.append(DaySchedule(
            date=orig_day.date,
            is_holiday=orig_day.is_holiday,
            morning=_names("Утро 08–17"),
            evening=_names("Вечер 15–00"),
            night=_names("Ночь 00–08"),
            workday=_names("Рабочий день"),
            day_off=day_off,
            vacation=vacation,
        ))

    # Пересчитываем метаданные
    meta = dict(schedule.metadata)
    meta["total_mornings"] = sum(len(d.morning) for d in new_days)
    meta["total_evenings"] = sum(len(d.evening) for d in new_days)
    meta["total_nights"]   = sum(len(d.night)   for d in new_days)
    return ScheduleModel(config=schedule.config, days=new_days, metadata=meta)


# ── Страница ──────────────────────────────────────────────────────────────────

st.set_page_config(page_title="График дежурств", page_icon="📅", layout="wide")
_init_state()

st.title("📅 График дежурств")

# ── Панель: загрузка конфига (sidebar) ───────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Конфигурация")

    uploaded = st.file_uploader(
        "Загрузить конфиг (.yaml)",
        type=["yaml", "yml"],
        help="Файл конфигурации, ранее сохранённый через кнопку «Скачать конфиг».",
    )
    if uploaded is not None:
        raw = uploaded.read().decode("utf-8")
        df_loaded, pins_loaded, co_loaded, m, y, s, err = _yaml_to_df(raw, st.session_state["cfg_year"])
        if err:
            st.error(err)
        else:
            st.session_state["employees_df"] = df_loaded
            st.session_state["pins_df"]      = pins_loaded
            st.session_state["carry_over"]   = co_loaded
            st.session_state["cfg_month"]    = m
            st.session_state["cfg_year"]     = y
            st.session_state["cfg_seed"]     = s
            _bump_table()
            msg = f"Загружен конфиг: {len(df_loaded)} сотрудников"
            if co_loaded:
                msg += f", перенос состояния для {len(co_loaded)} сотрудников"
            st.success(msg)
            st.rerun()

    st.divider()
    st.caption("Сохранить текущую конфигурацию:")

    # Кнопка скачивания — работает от текущего состояния таблицы.
    # Данные берём из session_state (data_editor записывает туда изменения).
    _table_key = f"{_TABLE_KEY_PREFIX}_{st.session_state['table_version']}"
    _current_df = st.session_state.get(_table_key, st.session_state["employees_df"])
    _cfg_month  = st.session_state.get("cfg_month", date.today().month)
    _cfg_year   = st.session_state.get("cfg_year",  date.today().year)
    _cfg_seed   = st.session_state.get("cfg_seed",  42)

    _current_pins_df = st.session_state.get("pins_df", pd.DataFrame([_EMPTY_PIN_ROW]))
    yaml_str = _df_to_yaml(_current_df, _cfg_month, _cfg_year, _cfg_seed, pins_df=_current_pins_df)
    st.download_button(
        label="⬇️ Скачать конфиг (.yaml)",
        data=yaml_str.encode("utf-8"),
        file_name=f"config_{_cfg_year}_{_cfg_month:02d}.yaml",
        mime="text/yaml",
        use_container_width=True,
    )

# ── Выбор периода ─────────────────────────────────────────────────────────────
col_m, col_y, _ = st.columns([2, 1, 6])
with col_m:
    month: int = st.selectbox(
        "Месяц",
        range(1, 13),
        index=st.session_state["cfg_month"] - 1,
        format_func=lambda m: MONTHS_RU[m - 1],
        key="cfg_month",
    )
with col_y:
    year: int = st.number_input(
        "Год", min_value=2024, max_value=2030,
        value=st.session_state["cfg_year"], step=1,
        key="cfg_year",
    )

st.divider()

# ── Таблица сотрудников ───────────────────────────────────────────────────────
st.subheader("Сотрудники")
st.caption(
    "Добавляйте строки кнопкой **+** снизу таблицы. "
    "Удалить строку — поставить галочку слева и нажать **Delete**. "
    "**Отпуск**: дд.мм–дд.мм, несколько через запятую."
)

_table_key = f"{_TABLE_KEY_PREFIX}_{st.session_state['table_version']}"
edited_df: pd.DataFrame = st.data_editor(
    st.session_state["employees_df"],
    column_config={
        "Имя":          st.column_config.TextColumn("Имя",          width="medium"),
        "Город":        st.column_config.SelectboxColumn("Город",   options=["Москва", "Хабаровск"], width="small"),
        "График":       st.column_config.SelectboxColumn("График",  options=["Гибкий", "5/2"],       width="small"),
        "Дежурный":     st.column_config.CheckboxColumn("Дежурный",     width="small"),
        "Только утро":  st.column_config.CheckboxColumn("Только утро",  width="small"),
        "Только вечер": st.column_config.CheckboxColumn("Только вечер", width="small"),
        "Тимлид":       st.column_config.CheckboxColumn("Тимлид",       width="small"),
        "Отпуск":       st.column_config.TextColumn("Отпуск (дд.мм–дд.мм)", width="large"),
        "Недоступен":   st.column_config.TextColumn("Недоступен (дд.мм,...)", width="large"),
    },
    num_rows="dynamic",
    use_container_width=True,
    key=_table_key,
)

# ── Правила: подсказка ────────────────────────────────────────────────────────
with st.expander("ℹ️ Правила заполнения"):
    st.markdown("""
| Поле | Описание |
|---|---|
| **Дежурный** | Участвует в дежурных сменах (утро/вечер для Москвы, ночь для Хабаровска) |
| **Только утро** | Назначается только на утренние смены (08:00–17:00 МСК) |
| **Только вечер** | Назначается только на вечерние смены (15:00–00:00 МСК) |
| **Тимлид** | Не дежурит (on_duty=False автоматически) |
| **5/2** | Не работает в субботу и воскресенье |
| **Отпуск** | Период(ы) отпуска: `10.03–20.03` или `10.03–15.03, 25.03–28.03` |
| **Недоступен** | Разовые недоступные дни (не отпуск): `10.03, 15.03` |

**Минимальный состав:** 4 дежурных в Москве, 2 дежурных в Хабаровске.
    """)

# ── Фиксированные назначения (пины) ──────────────────────────────────────────
with st.expander("📌 Фиксированные назначения"):
    st.caption(
        "Зафиксировать конкретного сотрудника на определённый день и смену. "
        "Формат даты: **дд.мм** (например `05.03`)."
    )
    pins_edited: pd.DataFrame = st.data_editor(
        st.session_state["pins_df"],
        column_config={
            "Дата":       st.column_config.TextColumn("Дата (дд.мм)", width="small"),
            "Сотрудник":  st.column_config.TextColumn("Сотрудник",    width="medium"),
            "Смена":      st.column_config.SelectboxColumn(
                "Смена", options=_SHIFTS_RU, width="small"
            ),
        },
        num_rows="dynamic",
        use_container_width=True,
        key="pins_table",
    )

# ── Дополнительные параметры ──────────────────────────────────────────────────
with st.expander("⚙️ Дополнительно"):
    seed: int = st.number_input(
        "Seed (для воспроизводимости результата)",
        min_value=0, value=st.session_state["cfg_seed"], step=1,
        key="cfg_seed",
        help="При одинаковом seed и тех же данных всегда получается одинаковый график.",
    )

st.divider()

# ── Кнопка генерации ──────────────────────────────────────────────────────────
if st.button("⚡ Сгенерировать расписание", type="primary", use_container_width=True):
    employees, errors = _build_employees(edited_df, year)

    if errors:
        for err in errors:
            st.error(err)
        st.stop()
    if not employees:
        st.warning("Добавьте хотя бы одного сотрудника.")
        st.stop()

    # Парсим пины
    pins: list[PinnedAssignment] = []
    for _, pin_row in pins_edited.iterrows():
        date_str = str(pin_row.get("Дата", "")).strip()
        emp_name = str(pin_row.get("Сотрудник", "")).strip()
        shift_ru = str(pin_row.get("Смена", "")).strip()
        if not date_str or not emp_name or not shift_ru:
            continue
        try:
            pin_date = datetime.strptime(f"{date_str}.{year}", "%d.%m.%Y").date()
        except ValueError:
            st.warning(f"Пин: неверный формат даты «{date_str}» — пропущен.")
            continue
        shift = _RU_TO_SHIFT.get(shift_ru)
        if shift is None:
            continue
        try:
            pins.append(PinnedAssignment(date=pin_date, employee_name=emp_name, shift=shift))
        except Exception as e:
            st.warning(f"Пин ({emp_name} / {date_str}): {e}")

    # Перенос состояния с предыдущего месяца
    carry_over_raw: list[dict] = st.session_state.get("carry_over", [])
    carry_over_objs: list[CarryOverState] = []
    for co in carry_over_raw:
        try:
            carry_over_objs.append(CarryOverState(**co))
        except Exception:
            pass

    try:
        config = Config(
            month=month, year=year, seed=seed,
            employees=employees, pins=pins, carry_over=carry_over_objs,
        )
    except Exception as e:
        st.error(f"Ошибка конфигурации: {e}")
        st.stop()

    with st.spinner("Загружаем производственный календарь (isdayoff.ru)…"):
        try:
            holidays = fetch_holidays(year, month)
        except CalendarError as e:
            st.error(f"Не удалось загрузить производственный календарь: {e}")
            st.info("Проверьте подключение к интернету.")
            st.stop()

    with st.spinner("Генерируем расписание…"):
        try:
            schedule = generate_schedule(config, holidays)
        except ScheduleError as e:
            st.error(f"Не удалось построить расписание: {e}")
            st.stop()

    meta = schedule.metadata
    st.success(
        f"✅ Расписание готово — {len(schedule.days)} дней, "
        f"{len(employees)} сотрудников, норма {meta.get('production_working_days', '?')} дн."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Утренних смен", meta.get("total_mornings", 0))
    c2.metric("Вечерних смен", meta.get("total_evenings", 0))
    c3.metric("Ночных смен",   meta.get("total_nights",   0))

    st.subheader("Редактирование расписания")
    st.caption(
        "Можно вручную изменить назначения. Имена сотрудников через запятую. "
        "Нажмите **⬇️ Скачать XLS** — в файл попадёт актуальная версия таблицы."
    )
    schedule_df = _schedule_to_edit_df(schedule)
    edited_schedule_df: pd.DataFrame = st.data_editor(
        schedule_df,
        column_config={
            "Дата":         st.column_config.TextColumn("Дата", disabled=True, width="small"),
            "Утро 08–17":   st.column_config.TextColumn("Утро 08–17",   width="large"),
            "Вечер 15–00":  st.column_config.TextColumn("Вечер 15–00",  width="large"),
            "Ночь 00–08":   st.column_config.TextColumn("Ночь 00–08",   width="large"),
            "Рабочий день": st.column_config.TextColumn("Рабочий день", width="large"),
        },
        use_container_width=True,
        hide_index=True,
        key="schedule_editor",
    )

    final_schedule = _edit_df_to_schedule(edited_schedule_df, schedule)

    with tempfile.TemporaryDirectory() as tmpdir:
        xls_path = export_xls(final_schedule, Path(tmpdir))
        xls_bytes = xls_path.read_bytes()

    st.download_button(
        label="⬇️ Скачать XLS",
        data=xls_bytes,
        file_name=f"schedule_{year}_{month:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )

    # Подготовить конфиг для следующего месяца с переносом состояний
    next_month = month % 12 + 1
    next_year = year + (1 if month == 12 else 0)
    final_carry_over: list[dict] = schedule.metadata.get("carry_over", [])
    _tbl_key = f"{_TABLE_KEY_PREFIX}_{st.session_state['table_version']}"
    _cur_df = st.session_state.get(_tbl_key, st.session_state["employees_df"])
    next_yaml = _df_to_yaml(
        _cur_df, next_month, next_year, seed,
        pins_df=None,
        carry_over=final_carry_over,
    )
    st.download_button(
        label=f"📅 Скачать конфиг для {MONTHS_RU[next_month - 1]} {next_year}",
        data=next_yaml.encode("utf-8"),
        file_name=f"config_{next_year}_{next_month:02d}.yaml",
        mime="text/yaml",
        use_container_width=True,
        help="Конфиг содержит состояния сотрудников на конец этого месяца, "
             "что обеспечивает корректный перенос серий смен в следующий месяц.",
    )
