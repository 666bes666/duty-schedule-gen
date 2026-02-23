"""Streamlit-интерфейс генератора графика дежурств."""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from duty_schedule.calendar import CalendarError, fetch_holidays
from duty_schedule.models import City, Config, Employee, ScheduleType, VacationPeriod
from duty_schedule.scheduler import ScheduleError, generate_schedule
from duty_schedule.export.xls import export_xls

# ── Константы ────────────────────────────────────────────────────────────────

MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

# Шаблон пустой строки в таблице
_EMPTY = {
    "Имя": "",
    "Город": "Москва",
    "График": "Гибкий",
    "Дежурный": True,
    "Только утро": False,
    "Только вечер": False,
    "Тимлид": False,
    "Отпуск": "",
}

# Начальные строки: 4 Москвы + 2 Хабаровска (минимум по правилам)
_DEFAULT_ROWS = [
    {**_EMPTY, "Город": "Москва"},
    {**_EMPTY, "Город": "Москва"},
    {**_EMPTY, "Город": "Москва"},
    {**_EMPTY, "Город": "Москва"},
    {**_EMPTY, "Город": "Хабаровск"},
    {**_EMPTY, "Город": "Хабаровск"},
]


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _parse_vacations(text: str, year: int, emp_name: str) -> tuple[list[VacationPeriod], str | None]:
    """Распарсить отпуска из строки вида «10.03–20.03, 25.03–31.03»."""
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


def _build_employees(df: pd.DataFrame, year: int) -> tuple[list[Employee], list[str]]:
    """Преобразовать DataFrame в список Employee. Возвращает (employees, errors)."""
    employees: list[Employee] = []
    errors: list[str] = []

    for _, row in df.iterrows():
        name = str(row["Имя"]).strip()
        if not name:
            continue  # пустые строки пропускаем молча

        city = City.MOSCOW if row["Город"] == "Москва" else City.KHABAROVSK
        stype = ScheduleType.FLEXIBLE if row["График"] == "Гибкий" else ScheduleType.FIVE_TWO

        vacations, err = _parse_vacations(str(row["Отпуск"]), year, name)
        if err:
            errors.append(err)
            continue

        try:
            employees.append(Employee(
                name=name,
                city=city,
                schedule_type=stype,
                on_duty=bool(row["Дежурный"]),
                morning_only=bool(row["Только утро"]),
                evening_only=bool(row["Только вечер"]),
                team_lead=bool(row["Тимлид"]),
                vacations=vacations,
            ))
        except Exception as e:
            errors.append(f"«{name}»: {e}")

    return employees, errors


# ── Страница ──────────────────────────────────────────────────────────────────

st.set_page_config(page_title="График дежурств", page_icon="📅", layout="wide")
st.title("📅 График дежурств")
st.caption("Заполните таблицу сотрудников и нажмите «Сгенерировать».")

# ── Выбор периода ─────────────────────────────────────────────────────────────
col_m, col_y, _ = st.columns([2, 1, 6])
with col_m:
    today = date.today()
    month: int = st.selectbox(
        "Месяц",
        range(1, 13),
        index=today.month - 1,
        format_func=lambda m: MONTHS_RU[m - 1],
    )
with col_y:
    year: int = st.number_input("Год", min_value=2024, max_value=2030, value=today.year, step=1)

st.divider()

# ── Таблица сотрудников ───────────────────────────────────────────────────────
st.subheader("Сотрудники")
st.caption(
    "Добавляйте строки кнопкой **+** снизу таблицы. "
    "Удалить строку — поставить галочку слева и нажать **Delete**. "
    "**Отпуск**: дд.мм–дд.мм, несколько через запятую (например: `10.03–20.03, 25.03–28.03`)."
)

edited_df: pd.DataFrame = st.data_editor(
    pd.DataFrame(_DEFAULT_ROWS),
    column_config={
        "Имя": st.column_config.TextColumn("Имя", width="medium"),
        "Город": st.column_config.SelectboxColumn(
            "Город", options=["Москва", "Хабаровск"], width="small",
        ),
        "График": st.column_config.SelectboxColumn(
            "График", options=["Гибкий", "5/2"], width="small",
        ),
        "Дежурный":    st.column_config.CheckboxColumn("Дежурный",    width="small"),
        "Только утро": st.column_config.CheckboxColumn("Только утро", width="small"),
        "Только вечер":st.column_config.CheckboxColumn("Только вечер",width="small"),
        "Тимлид":      st.column_config.CheckboxColumn("Тимлид",      width="small"),
        "Отпуск": st.column_config.TextColumn("Отпуск (дд.мм–дд.мм)", width="large"),
    },
    num_rows="dynamic",
    use_container_width=True,
    key="employees_table",
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

**Минимальный состав:** 4 дежурных в Москве, 2 дежурных в Хабаровске.
    """)

# ── Дополнительные параметры ──────────────────────────────────────────────────
with st.expander("⚙️ Дополнительно"):
    seed: int = st.number_input(
        "Seed (для воспроизводимости результата)",
        min_value=0, value=42, step=1,
        help="При одинаковом seed и тех же данных всегда получается одинаковый график.",
    )

st.divider()

# ── Кнопка генерации ──────────────────────────────────────────────────────────
generate = st.button(
    "⚡ Сгенерировать расписание",
    type="primary",
    use_container_width=True,
)

if generate:
    # 1. Собрать сотрудников
    employees, errors = _build_employees(edited_df, year)

    if errors:
        for err in errors:
            st.error(err)
        st.stop()

    if not employees:
        st.warning("Добавьте хотя бы одного сотрудника.")
        st.stop()

    # 2. Проверить конфигурацию
    try:
        config = Config(month=month, year=year, seed=seed, employees=employees)
    except Exception as e:
        st.error(f"Ошибка конфигурации: {e}")
        st.stop()

    # 3. Загрузить производственный календарь
    with st.spinner("Загружаем производственный календарь (isdayoff.ru)…"):
        try:
            holidays = fetch_holidays(year, month)
        except CalendarError as e:
            st.error(f"Не удалось загрузить производственный календарь: {e}")
            st.info("Проверьте подключение к интернету.")
            st.stop()

    # 4. Генерировать расписание
    with st.spinner("Генерируем расписание…"):
        try:
            schedule = generate_schedule(config, holidays)
        except ScheduleError as e:
            st.error(f"Не удалось построить расписание: {e}")
            st.stop()

    # 5. Экспорт в XLS
    with tempfile.TemporaryDirectory() as tmpdir:
        xls_path = export_xls(schedule, Path(tmpdir))
        xls_bytes = xls_path.read_bytes()

    # 6. Результат
    meta = schedule.metadata
    st.success(
        f"✅ Расписание готово — {len(schedule.days)} дней, "
        f"{len(employees)} сотрудников, норма {meta.get('production_working_days', '?')} дн."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Утренних смен",  meta.get("total_mornings", 0))
    c2.metric("Вечерних смен",  meta.get("total_evenings", 0))
    c3.metric("Ночных смен",    meta.get("total_nights",   0))

    st.download_button(
        label="⬇️ Скачать XLS",
        data=xls_bytes,
        file_name=f"schedule_{year}_{month:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )
