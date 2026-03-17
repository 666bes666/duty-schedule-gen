from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from duty_schedule.calendar import CalendarError, compute_short_days, fetch_holidays
from duty_schedule.export.xls import export_xls
from duty_schedule.models import (
    CarryOverState,
    Config,
    PinnedAssignment,
    collect_config_issues,
)
from duty_schedule.scheduler import ScheduleError, generate_schedule
from duty_schedule.stats import build_assignments, compute_stats
from duty_schedule.ui.builders import (
    _build_employees,
    _edit_df_to_schedule,
    _schedule_to_edit_df,
    _validate_config,
    _validate_edited_schedule,
)
from duty_schedule.ui.config_io import (
    _df_to_yaml,
    _yaml_to_df,
)
from duty_schedule.ui.mappings import (
    _EMPTY_ROW,
    _RU_TO_SHIFT,
    _SHIFTS_RU,
    _TABLE_KEY_PREFIX,
    _WEEKDAY_INT_TO_RU,
    _WEEKDAY_OPTIONS,
    _WEEKDAY_RU_TO_INT,
    _XLS_VERSION,
    MONTHS_RU,
)
from duty_schedule.ui.state import (
    _bump_table,
    _get_emp_dates,
    _init_state,
)
from duty_schedule.ui.views import (
    _render_calendar,
    _render_changelog,
    _render_load_dashboard,
    _render_schedule_diff,
    _render_whatif_panel,
    render_employee_ics_downloads,
)
from duty_schedule.xls_import import XlsImportError, parse_carry_over_from_xls

st.set_page_config(page_title="График дежурств", page_icon=None, layout="wide")
_init_state()

st.markdown(
    """
<style>
:root {
    --fs-section:    1.05rem;
    --fs-tab:        0.9rem;
    --fs-body:       0.875rem;
    --fs-caption:    0.78rem;
    --fs-alert:      0.82rem;
}

/* Tabs: full-width stretch */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    width: 100%;
    display: flex;
}
.stTabs [data-baseweb="tab"] {
    flex: 1 1 0;
    justify-content: center;
    height: 2.75rem;
    padding: 0 1rem;
    font-size: var(--fs-tab);
    font-weight: 600;
    border-radius: 4px 4px 0 0;
}

/* Section headers (st.subheader → h3) */
h3 {
    font-size: var(--fs-section) !important;
    font-weight: 600 !important;
    margin-top: 0.75rem !important;
    margin-bottom: 0.25rem !important;
}

/* Captions */
.stCaption, small {
    font-size: var(--fs-caption) !important;
}

/* Alert banners */
.stAlert > div {
    padding: 0.45rem 0.75rem !important;
    font-size: var(--fs-alert) !important;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("График дежурств")

with st.sidebar:
    st.header("Конфигурация")

    uploaded = st.file_uploader(
        "Загрузить конфиг (.yaml)",
        type=["yaml", "yml"],
        help="Файл конфигурации, ранее сохранённый через кнопку «Скачать конфиг».",
    )
    if uploaded is not None:
        raw = uploaded.read().decode("utf-8")
        df_loaded, pins_loaded, co_loaded, m, y, s, emp_dates_loaded, err = _yaml_to_df(
            raw, st.session_state["cfg_year"]
        )
        if err:
            st.error(err)
        else:
            st.session_state["employee_dates"] = {}
            st.session_state["last_result"] = None
            st.session_state["employees_df"] = df_loaded
            st.session_state["pins_df"] = pins_loaded
            st.session_state["carry_over"] = co_loaded
            st.session_state["cfg_month"] = m
            st.session_state["cfg_year"] = y
            st.session_state["cfg_seed"] = s
            st.session_state["employee_dates"] = emp_dates_loaded
            st.session_state["_df_for_download"] = df_loaded
            st.session_state["_pins_for_download"] = pins_loaded
            _bump_table()
            msg = f"Загружен конфиг: {len(df_loaded)} сотрудников"
            if co_loaded:
                msg += f", перенос состояния для {len(co_loaded)} сотрудников"
            st.success(msg)
            st.rerun()

    st.divider()
    st.markdown("**Сохранить конфигурацию**")

    _dl_df = st.session_state["_df_for_download"]
    _dl_pins = st.session_state["_pins_for_download"]
    _cfg_month = st.session_state.get("cfg_month", date.today().month)
    _cfg_year = st.session_state.get("cfg_year", date.today().year)
    _cfg_seed = st.session_state.get("cfg_seed", 42)

    yaml_str = _df_to_yaml(
        _dl_df,
        _cfg_month,
        _cfg_year,
        _cfg_seed,
        employee_dates=st.session_state["employee_dates"],
        pins_df=_dl_pins,
    )
    st.download_button(
        label="Скачать конфиг (.yaml)",
        data=yaml_str.encode("utf-8"),
        file_name=f"config_{_cfg_year}_{_cfg_month:02d}.yaml",
        mime="text/yaml",
        use_container_width=True,
    )

    st.divider()
    st.markdown("**Перенос состояния из прошлого месяца**")
    xls_uploaded = st.file_uploader(
        "Загрузить график предыдущего месяца (.xlsx)",
        type=["xlsx"],
        help="XLS-файл с графиком дежурств за прошлый месяц. "
        "Из него будет автоматически извлечено состояние сотрудников.",
    )
    if xls_uploaded is not None:
        try:
            carry_list = parse_carry_over_from_xls(xls_uploaded.read())
        except XlsImportError as exc:
            st.error(str(exc))
        else:
            co_dicts = [co.model_dump() for co in carry_list]
            st.session_state["carry_over"] = co_dicts
            st.success(f"Загружено состояние для {len(carry_list)} сотрудников")
            with st.expander("Предпросмотр carry-over"):
                _co_rows = []
                for co in carry_list:
                    _co_rows.append(
                        {
                            "Имя": co.employee_name,
                            "Посл. смена": co.last_shift.value if co.last_shift else "—",
                            "Раб. подряд": co.consecutive_working,
                            "Вых. подряд": co.consecutive_off,
                            "Однотип. подряд": co.consecutive_same_shift,
                        }
                    )
                st.dataframe(pd.DataFrame(_co_rows), use_container_width=True, hide_index=True)

col_m, col_y, _ = st.columns([2, 1, 6])
with col_m:
    month: int = st.selectbox(
        "Месяц",
        range(1, 13),
        format_func=lambda m: MONTHS_RU[m - 1],
        key="cfg_month",
    )
with col_y:
    year: int = st.number_input(
        "Год",
        min_value=2024,
        max_value=2030,
        step=1,
        key="cfg_year",
    )

st.caption("Заполните все три раздела, затем нажмите «Сгенерировать расписание» ниже.")

_setup_tab1, _setup_tab2, _setup_tab3 = st.tabs(["1. Состав", "2. Ограничения", "3. Пины"])

with _setup_tab1:
    st.subheader("Сотрудники")
    st.caption(
        "Добавляйте строки кнопкой **+** снизу. Удалить строку — галочка слева + **Delete**."
    )

    _gopt_key = f"_gopt_{st.session_state['table_version']}"
    if _gopt_key not in st.session_state:
        st.session_state[_gopt_key] = [""] + sorted(
            {
                str(r["Имя"]).strip()
                for _, r in st.session_state["employees_df"].iterrows()
                if str(r["Имя"]).strip()
            }
        )
    _group_options: list[str] = st.session_state[_gopt_key]

    _sort_cols = st.columns([3, 1, 1])
    _sort_by = _sort_cols[0].selectbox(
        "Сортировать по столбцу",
        options=["—", "По умолчанию", "Имя", "Город", "График", "Дежурный", "Загрузка%"],
        key="sort_by_col",
        label_visibility="collapsed",
    )
    _sort_asc = (
        _sort_cols[1].radio(
            "Направление",
            ["↑ А→Я", "↓ Я→А"],
            key="sort_dir",
            horizontal=False,
            label_visibility="collapsed",
        )
        == "↑ А→Я"
    )
    _sort_pressed = _sort_cols[2].button(
        "Сортировать",
        use_container_width=True,
        key="sort_btn",
    )
    if _sort_pressed and _sort_by != "—":
        _cur_df = st.session_state.get("_df_for_download", st.session_state["employees_df"])
        if _sort_by == "По умолчанию":
            _city_order = {"Москва": 0, "Хабаровск": 1}
            _stype_order = {"5/2": 0, "Гибкий": 1}
            _cur_df = _cur_df.copy()
            _cur_df["_s1"] = _cur_df["Город"].map(_city_order).fillna(2)
            _cur_df["_s2"] = _cur_df["Дежурный"].astype(int)
            _cur_df["_s3"] = _cur_df["График"].map(_stype_order).fillna(2)
            st.session_state["employees_df"] = (
                _cur_df.sort_values(["_s1", "_s2", "_s3", "Имя"])
                .drop(columns=["_s1", "_s2", "_s3"])
                .reset_index(drop=True)
            )
        else:
            st.session_state["employees_df"] = _cur_df.sort_values(
                _sort_by, ascending=_sort_asc
            ).reset_index(drop=True)
        _bump_table()
        st.rerun()

    _table_key = f"{_TABLE_KEY_PREFIX}_{st.session_state['table_version']}"
    _base_df = st.session_state["employees_df"]
    _display_df = _base_df.copy()
    _display_df.insert(0, "№", range(1, len(_display_df) + 1))
    _edited_raw: pd.DataFrame = st.data_editor(
        _display_df,
        column_config={
            "№": st.column_config.NumberColumn("№"),
            "Имя": st.column_config.TextColumn("Имя"),
            "Город": st.column_config.SelectboxColumn(
                "Город",
                options=["Москва", "Хабаровск"],
            ),
            "График": st.column_config.SelectboxColumn(
                "График",
                options=["Гибкий", "5/2"],
            ),
            "Дежурный": st.column_config.CheckboxColumn(
                "Деж.",
                help="Участвует в назначении дежурных смен",
            ),
            "Всегда на деж.": st.column_config.CheckboxColumn(
                "Всегда",
                help=(
                    "Назначается на дежурство каждый доступный "
                    "рабочий день. Требует: Деж.=✓, Город=Москва, "
                    "указан тип смены (Утро▲ или Вечер▲)."
                ),
            ),
            "Только утро": st.column_config.CheckboxColumn(
                "Утро▲",
                help="Только утренние смены 08:00–17:00 МСК",
            ),
            "Только вечер": st.column_config.CheckboxColumn(
                "Вечер▲",
                help="Только вечерние смены 15:00–00:00 МСК",
            ),
            "Предпочт. смена": st.column_config.SelectboxColumn(
                "Пред. смена",
                options=["", "Утро", "Вечер", "Ночь", "Рабочий день"],
                help="Предпочтительная смена (мягкий приоритет)",
            ),
            "Загрузка%": st.column_config.NumberColumn(
                "Загр.%",
                min_value=1,
                max_value=100,
                step=1,
                help="Норма нагрузки: 100 = полная ставка, 50 = полставки",
            ),
            "Макс. утренних": st.column_config.NumberColumn(
                "↑Утр",
                min_value=1,
                step=1,
                help="Макс. утренних смен в месяц (пусто = без ограничений)",
            ),
            "Макс. вечерних": st.column_config.NumberColumn(
                "↑Веч",
                min_value=1,
                step=1,
                help="Макс. вечерних смен в месяц (пусто = без ограничений)",
            ),
            "Макс. ночных": st.column_config.NumberColumn(
                "↑Ноч",
                min_value=1,
                step=1,
                help="Макс. ночных смен в месяц (пусто = без ограничений)",
            ),
            "Макс. подряд": st.column_config.NumberColumn(
                "↑Подряд",
                min_value=1,
                step=1,
                help="Макс. рабочих дней подряд (пусто = 5)",
            ),
            "Группа": st.column_config.SelectboxColumn(
                "Группа",
                options=_group_options,
                help="Сотрудников одной группы не ставят вместе на одну смену",
            ),
        },
        column_order=[
            "№",
            "Имя",
            "Город",
            "График",
            "Дежурный",
            "Всегда на деж.",
            "Только утро",
            "Только вечер",
            "Предпочт. смена",
            "Загрузка%",
            "Макс. утренних",
            "Макс. вечерних",
            "Макс. ночных",
            "Макс. подряд",
            "Группа",
        ],
        disabled=["№"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=_table_key,
    )
    edited_df = _edited_raw.drop(columns=["№"], errors="ignore").reset_index(drop=True)
    st.session_state["_df_for_download"] = edited_df

    st.caption("Быстро добавить сотрудника с типовыми настройками:")
    _pr1, _pr2, _pr3 = st.columns(3)
    if _pr1.button("+ Москва, дежурный", use_container_width=True, key="preset_msk"):
        _preset_row = {**_EMPTY_ROW, "Город": "Москва", "Дежурный": True}
        st.session_state["employees_df"] = pd.concat(
            [edited_df, pd.DataFrame([_preset_row])],
            ignore_index=True,
        )
        _bump_table()
        st.rerun()
    if _pr2.button("+ Хабаровск, ночной", use_container_width=True, key="preset_khb"):
        _preset_row = {**_EMPTY_ROW, "Город": "Хабаровск", "Дежурный": True}
        st.session_state["employees_df"] = pd.concat(
            [edited_df, pd.DataFrame([_preset_row])],
            ignore_index=True,
        )
        _bump_table()
        st.rerun()
    if _pr3.button("+ Не дежурит (5/2)", use_container_width=True, key="preset_nodty"):
        _preset_row = {**_EMPTY_ROW, "Дежурный": False, "График": "5/2"}
        st.session_state["employees_df"] = pd.concat(
            [edited_df, pd.DataFrame([_preset_row])],
            ignore_index=True,
        )
        _bump_table()
        st.rerun()

    with st.expander("Массовое редактирование"):
        _bulk_names = [
            str(r["Имя"]).strip() for _, r in edited_df.iterrows() if str(r["Имя"]).strip()
        ]
        _bulk_selected = st.multiselect(
            "Сотрудники",
            options=_bulk_names,
            key="bulk_employees",
        )
        _bulk_columns = [
            "Город",
            "График",
            "Дежурный",
            "Всегда на деж.",
            "Только утро",
            "Только вечер",
            "Предпочт. смена",
            "Загрузка%",
            "Макс. утренних",
            "Макс. вечерних",
            "Макс. ночных",
            "Макс. подряд",
            "Группа",
        ]
        _bulk_col = st.selectbox(
            "Столбец",
            options=_bulk_columns,
            key="bulk_column",
        )
        _bulk_value = None
        if _bulk_col == "Город":
            _bulk_value = st.selectbox("Значение", ["Москва", "Хабаровск"], key="bulk_val")
        elif _bulk_col == "График":
            _bulk_value = st.selectbox("Значение", ["Гибкий", "5/2"], key="bulk_val")
        elif _bulk_col in ("Дежурный", "Всегда на деж.", "Только утро", "Только вечер"):
            _bulk_value = st.checkbox("Значение", key="bulk_val")
        elif _bulk_col == "Предпочт. смена":
            _bulk_value = st.selectbox(
                "Значение",
                ["", "Утро", "Вечер", "Ночь", "Рабочий день"],
                key="bulk_val",
            )
        elif _bulk_col == "Загрузка%":
            _bulk_value = st.number_input(
                "Значение",
                min_value=1,
                max_value=100,
                value=100,
                step=1,
                key="bulk_val",
            )
        elif _bulk_col in ("Макс. утренних", "Макс. вечерних", "Макс. ночных", "Макс. подряд"):
            _bulk_value = st.number_input("Значение", min_value=1, value=6, step=1, key="bulk_val")
        elif _bulk_col == "Группа":
            _bulk_value = st.text_input("Значение", key="bulk_val")

        if st.button("Применить", key="bulk_apply", disabled=not _bulk_selected):
            _bulk_df = edited_df.copy()
            _mask = _bulk_df["Имя"].astype(str).str.strip().isin(_bulk_selected)
            _bulk_df.loc[_mask, _bulk_col] = _bulk_value
            st.session_state["employees_df"] = _bulk_df
            _bump_table()
            st.rerun()

    with st.expander("Лимит однотипных смен подряд"):
        st.caption(
            "Ограничить число одинаковых дежурных смен подряд. "
            "Применяется ко всем дежурным с гибким графиком."
        )
        _consec_mask = (
            edited_df["Имя"].astype(str).str.strip().ne("")
            & edited_df["Дежурный"].fillna(True).astype(bool)
            & (edited_df["График"].astype(str) == "Гибкий")
        )
        if not _consec_mask.any():
            st.info("Нет дежурных с гибким графиком.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                _unlim_m = st.checkbox("Без лимита", value=True, key="consec_morning_unlim")
                _raw_m = st.number_input(
                    "Подряд: утро",
                    min_value=1,
                    step=1,
                    value=3,
                    disabled=_unlim_m,
                    key="consec_morning",
                )
                _v_m = None if _unlim_m else _raw_m
            with c2:
                _unlim_e = st.checkbox("Без лимита", value=True, key="consec_evening_unlim")
                _raw_e = st.number_input(
                    "Подряд: вечер",
                    min_value=1,
                    step=1,
                    value=3,
                    disabled=_unlim_e,
                    key="consec_evening",
                )
                _v_e = None if _unlim_e else _raw_e
            with c3:
                _unlim_w = st.checkbox("Без лимита", value=True, key="consec_workday_unlim")
                _raw_w = st.number_input(
                    "Подряд: день",
                    min_value=1,
                    step=1,
                    value=3,
                    disabled=_unlim_w,
                    key="consec_workday",
                )
                _v_w = None if _unlim_w else _raw_w
            if st.button("Применить ко всем дежурным", key="consec_save"):
                _upd = edited_df.copy()
                _upd.loc[_consec_mask, "Подряд: утро"] = _v_m
                _upd.loc[_consec_mask, "Подряд: вечер"] = _v_e
                _upd.loc[_consec_mask, "Подряд: день"] = _v_w
                st.session_state["employees_df"] = _upd
                _bump_table()
                st.rerun()

with _setup_tab2:
    _emp_names = [str(r["Имя"]).strip() for _, r in edited_df.iterrows() if str(r["Имя"]).strip()]

    if not _emp_names:
        st.info("Сначала добавьте сотрудников на вкладке **1. Состав**.")
    else:
        _sel = st.selectbox("Сотрудник", _emp_names, key="date_emp_selector")
        _cfg = _get_emp_dates(_sel)

        _emp_row = edited_df[edited_df["Имя"].astype(str).str.strip() == _sel]
        if not _emp_row.empty:
            _er = _emp_row.iloc[0]
            _sc1, _sc2, _sc3, _sc4 = st.columns(4)
            _sc1.metric("Город", _er["Город"])
            _sc2.metric("График", _er["График"])
            _sc3.metric("Загрузка", f"{int(_er.get('Загрузка%') or 100)}%")
            _sc4.metric("Группа", str(_er.get("Группа", "") or "—"))
            _flags: list[str] = []
            if _er.get("Дежурный"):
                _flags.append("Дежурный")
            if _er.get("Всегда на деж.", False):
                _flags.append("Всегда на деж.")
            if _er.get("Только утро"):
                _flags.append("Только утро")
            if _er.get("Только вечер"):
                _flags.append("Только вечер")
            _flag_str = "  ·  ".join(_flags) if _flags else "—"
            _pref = str(_er.get("Предпочт. смена", "")).strip()
            _detail_parts = [f"Флаги: {_flag_str}"]
            if _pref:
                _detail_parts.append(f"Предпочт. смена: {_pref}")
            st.caption("  ·  ".join(_detail_parts))

        st.divider()

        st.subheader("Отпуска")
        _vac_del: list[int] = []
        for _i, (_vs, _ve) in enumerate(_cfg["vacations"]):
            _c1, _c2, _c3 = st.columns([4, 4, 1])
            with _c1:
                _new_vs = st.date_input(
                    "Начало",
                    value=_vs,
                    key=f"vs_{_sel}_{_i}",
                    label_visibility="collapsed",
                )
            with _c2:
                _new_ve = st.date_input(
                    "Конец",
                    value=_ve if _ve >= _new_vs else _new_vs,
                    min_value=_new_vs,
                    key=f"ve_{_sel}_{_i}",
                    label_visibility="collapsed",
                )
            _cfg["vacations"][_i] = (_new_vs, _new_ve)
            with _c3:
                if st.button("×", key=f"vdel_{_sel}_{_i}", help="Удалить период"):
                    _vac_del.append(_i)

        for _i in reversed(_vac_del):
            _cfg["vacations"].pop(_i)
            st.rerun()

        if st.button("+ Добавить период отпуска", key=f"vadd_{_sel}"):
            _cfg["vacations"].append((date(year, month, 1), date(year, month, 7)))
            st.rerun()

        st.divider()

        st.subheader("Недоступные дни")
        st.caption("Не отпуск — разовые блокировки")
        _unavail_del: list[int] = []
        for _i, _ud in enumerate(_cfg["unavailable"]):
            _c1, _c2 = st.columns([8, 1])
            with _c1:
                _new_ud = st.date_input(
                    "Дата",
                    value=_ud,
                    key=f"ud_{_sel}_{_i}",
                    label_visibility="collapsed",
                )
            _cfg["unavailable"][_i] = _new_ud
            with _c2:
                if st.button("×", key=f"udel_{_sel}_{_i}", help="Удалить дату"):
                    _unavail_del.append(_i)

        for _i in reversed(_unavail_del):
            _cfg["unavailable"].pop(_i)
            st.rerun()

        if st.button("+ Добавить недоступный день", key=f"uadd_{_sel}"):
            _cfg["unavailable"].append(date(year, month, 1))
            st.rerun()

        st.divider()

        st.subheader("Постоянные выходные дни недели")
        st.caption("Сотрудник не будет назначаться в эти дни недели каждую неделю.")
        _current_days_off = _cfg.get("days_off_weekly", [])
        _current_labels = [
            _WEEKDAY_INT_TO_RU[d] for d in _current_days_off if d in _WEEKDAY_INT_TO_RU
        ]
        _new_days_labels = st.multiselect(
            "Выберите дни",
            options=_WEEKDAY_OPTIONS,
            default=_current_labels,
            key=f"days_off_{_sel}",
            label_visibility="collapsed",
        )
        _cfg["days_off_weekly"] = [_WEEKDAY_RU_TO_INT[d] for d in _new_days_labels]

    st.divider()

    with st.expander("Правила заполнения"):
        st.markdown("""
| Поле | Описание |
|---|---|
| **Дежурный** | Участвует в дежурных сменах (утро/вечер для Москвы, ночь для Хабаровска) |
| **Только утро** | Назначается только на утренние смены (08:00–17:00 МСК) |
| **Только вечер** | Назначается только на вечерние смены (15:00–00:00 МСК) |
| **5/2** | Не работает в субботу и воскресенье |
| **Предпочт. смена** | Мягкий приоритет при выборе смены (не гарантирует назначение) |
| **Загрузка%** | Норма нагрузки: 100 = полная ставка, 50 = полставки |
| **Макс. утр./веч./ноч.** | Лимит смен данного типа в месяц (пусто = без ограничений) |
| **Макс. подряд** | Индивидуальный лимит рабочих дней подряд (пусто = 5) |
| **Подряд: утро/вечер/день** | Настраивается в разделе «Лимит однотипных смен подряд» ниже |
| **Группа** | Не ставить двух из одной группы на одну смену в один день |

**Минимальный состав:** 4 дежурных в Москве, 2 дежурных в Хабаровске.
        """)

with _setup_tab3:
    st.subheader("Фиксированные назначения")
    st.caption("Зафиксировать конкретного сотрудника на определённый день и смену.")
    pins_edited: pd.DataFrame = st.data_editor(
        st.session_state["pins_df"],
        column_config={
            "Дата": st.column_config.DateColumn(
                "Дата",
                format="DD.MM",
                width="small",
                help="Выберите дату через календарь",
            ),
            "Сотрудник": st.column_config.TextColumn("Сотрудник", width="medium"),
            "Смена": st.column_config.SelectboxColumn("Смена", options=_SHIFTS_RU, width="small"),
        },
        num_rows="dynamic",
        use_container_width=True,
        key="pins_table",
    )
    st.session_state["_pins_for_download"] = pins_edited

    st.divider()

    seed: int = st.number_input(
        "Seed (для воспроизводимости результата)",
        min_value=0,
        step=1,
        key="cfg_seed",
        help="При одинаковом seed и тех же данных всегда получается одинаковый график.",
    )

    _solver_choice = st.radio(
        "Алгоритм",
        ["greedy", "cpsat"],
        key="cfg_solver",
        horizontal=True,
        help="greedy — жадный с постобработкой; cpsat — CP-SAT solver (OR-Tools, если установлен)",
    )

st.divider()

_multi_mode = st.toggle("Мультимесячное планирование", value=False, key="multi_mode")
if _multi_mode:
    _mc1, _mc2, _mc3, _mc4 = st.columns(4)
    _multi_start_m = _mc1.selectbox(
        "Начало (месяц)",
        range(1, 13),
        format_func=lambda m: MONTHS_RU[m - 1],
        key="multi_start_m",
    )
    _multi_start_y = _mc2.number_input(
        "Год начала", min_value=2024, max_value=2030, key="multi_start_y"
    )
    _multi_end_m = _mc3.selectbox(
        "Конец (месяц)",
        range(1, 13),
        format_func=lambda m: MONTHS_RU[m - 1],
        key="multi_end_m",
    )
    _multi_end_y = _mc4.number_input("Год конца", min_value=2024, max_value=2030, key="multi_end_y")

_val_errors, _val_warnings = _validate_config(edited_df)
for _verr in _val_errors:
    st.error(_verr)
for _vwarn in _val_warnings:
    st.warning(_vwarn)

if st.button("Сгенерировать расписание", type="primary", use_container_width=True):
    employees, errors = _build_employees(
        edited_df, employee_dates=st.session_state["employee_dates"]
    )

    if errors:
        for err in errors:
            st.error(err)
        st.stop()
    if not employees:
        st.warning("Добавьте хотя бы одного сотрудника.")
        st.stop()

    pins: list[PinnedAssignment] = []
    for _, pin_row in pins_edited.iterrows():
        raw_date = pin_row.get("Дата")
        emp_name = str(pin_row.get("Сотрудник", "")).strip()
        shift_ru = str(pin_row.get("Смена", "")).strip()
        if not raw_date or not emp_name or not shift_ru:
            continue
        if isinstance(raw_date, date):
            pin_date = raw_date
        else:
            try:
                pin_date = datetime.strptime(f"{str(raw_date).strip()}.{year}", "%d.%m.%Y").date()
            except ValueError:
                st.warning(f"Пин: неверный формат даты «{raw_date}» — пропущен.")
                continue
        shift = _RU_TO_SHIFT.get(shift_ru)
        if shift is None:
            continue
        try:
            pins.append(PinnedAssignment(date=pin_date, employee_name=emp_name, shift=shift))
        except (ValueError, ValidationError) as exc:
            st.warning(f"Пин ({emp_name} / {raw_date}): {exc}")

    carry_over_raw: list[dict] = st.session_state.get("carry_over", [])
    carry_over_objs: list[CarryOverState] = []
    for co in carry_over_raw:
        try:
            carry_over_objs.append(CarryOverState(**co))
        except (ValueError, ValidationError) as exc:
            st.warning(f"Carry-over: ошибка валидации — {exc}")

    emp_names = {e.name for e in employees}
    matched = [co for co in carry_over_objs if co.employee_name in emp_names]
    skipped = len(carry_over_objs) - len(matched)
    if skipped and matched:
        st.info(
            f"Carry-over: применено для {len(matched)} из {len(carry_over_objs)} сотрудников "
            f"({skipped} не найдены в текущем составе)."
        )
    elif skipped and not matched:
        st.warning(
            f"Carry-over: ни один из {len(carry_over_objs)} сотрудников "
            "не найден в текущем составе. Имена должны совпадать точно."
        )
    carry_over_objs = matched

    _solver_val = st.session_state.get("cfg_solver", "greedy")
    try:
        config = Config(
            month=month,
            year=year,
            seed=seed,
            employees=employees,
            pins=pins,
            carry_over=carry_over_objs,
            solver=_solver_val,
        )
    except (ValueError, ValidationError) as exc:
        st.error(f"Ошибка конфигурации: {exc}")
        st.stop()

    cfg_errors, cfg_warnings = collect_config_issues(config)
    if cfg_errors:
        for msg in cfg_errors:
            st.error(msg)
        for msg in cfg_warnings:
            st.warning(msg)
        st.stop()
    for msg in cfg_warnings:
        st.warning(msg)

    with st.spinner("Загружаем производственный календарь (isdayoff.ru)…"):
        try:
            holidays, short_days = fetch_holidays(year, month)
        except CalendarError:
            import calendar as _cal

            _, _n_days = _cal.monthrange(year, month)
            holidays = {
                date(year, month, d)
                for d in range(1, _n_days + 1)
                if date(year, month, d).weekday() >= 5
            }
            short_days = compute_short_days(year, month, holidays)
            st.warning(
                "Не удалось загрузить производственный календарь. "
                "Праздничные дни не учтены — только суббота/воскресенье."
            )

    from duty_schedule.validation import validate_pre_generation

    pre_errors, pre_warnings = validate_pre_generation(config, holidays)
    if pre_errors:
        for msg in pre_errors:
            st.error(msg)
        for msg in pre_warnings:
            st.warning(msg)
        st.stop()
    for msg in pre_warnings:
        st.warning(msg)

    with st.spinner("Генерируем расписание…"):
        try:
            schedule = generate_schedule(config, holidays)
        except ScheduleError as e:
            st.error(f"Не удалось построить расписание: {e}")
            st.stop()

    next_month = month % 12 + 1
    next_year = year + (1 if month == 12 else 0)
    final_carry_over: list[dict] = schedule.metadata.get("carry_over", [])
    next_yaml = _df_to_yaml(
        edited_df,
        next_month,
        next_year,
        seed,
        employee_dates=st.session_state["employee_dates"],
        pins_df=None,
        carry_over=final_carry_over,
    )

    st.session_state["last_result"] = {
        "schedule": schedule,
        "schedule_df": _schedule_to_edit_df(schedule),
        "meta": dict(schedule.metadata),
        "next_month": next_month,
        "next_year": next_year,
        "next_yaml": next_yaml,
        "gen_at": datetime.now().strftime("%d.%m %H:%M"),
        "emp_count": len(employees),
        "gen_month": month,
        "gen_year": year,
        "emp_df_snap": edited_df.copy(),
        "short_days": short_days,
        "holidays": holidays,
    }

    _history: list[dict] = st.session_state["schedule_history"]
    _gen_label = f"{MONTHS_RU[month - 1]} {year} @ {datetime.now().strftime('%H:%M:%S')}"
    _history.append({"label": _gen_label, "schedule": schedule})
    if len(_history) > 5:
        st.session_state["schedule_history"] = _history[-5:]

if st.session_state.get("last_result"):
    _res = st.session_state["last_result"]
    _schedule = _res["schedule"]
    _meta = _res["meta"]

    st.success(
        f"{MONTHS_RU[_res['gen_month'] - 1]} {_res['gen_year']} — "
        f"{len(_schedule.days)} дней, {_res['emp_count']} сотрудников, "
        f"норма {_meta.get('production_working_days', '?')} дн. "
        f"· сгенерировано в {_res['gen_at']}"
    )

    _total_workdays = sum(len(d.workday) for d in _schedule.days)
    _total_dayoffs = sum(len(d.day_off) for d in _schedule.days)
    _total_vacations = sum(len(d.vacation) for d in _schedule.days)

    _rc1, _rc2, _rc3 = st.columns(3)
    _rc1.metric("Утренних смен", _meta.get("total_mornings", 0))
    _rc2.metric("Вечерних смен", _meta.get("total_evenings", 0))
    _rc3.metric("Ночных смен", _meta.get("total_nights", 0))

    _rc4, _rc5, _rc6 = st.columns(3)
    _rc4.metric("Рабочих дней", _total_workdays)
    _rc5.metric("Выходных", _total_dayoffs)
    _rc6.metric("Отпусков", _total_vacations)

    _prod_days = int(_meta.get("production_working_days", 21))
    _assignments = build_assignments(_schedule)
    _short_days = _res.get("short_days")
    _stats_list = compute_stats(_schedule, _assignments, _prod_days, short_days=_short_days)

    _total_isolated = sum(s.isolated_off for s in _stats_list)
    _max_streak = max((s.max_streak_work for s in _stats_list), default=0)
    _weekend_work_total = sum(s.weekend_work for s in _stats_list)

    _rc7, _rc8, _rc9 = st.columns(3)
    _rc7.metric("Изолированных выходных", _total_isolated)
    _rc8.metric("Макс. серия работы", _max_streak)
    _rc9.metric("Работа в выходные", _weekend_work_total)

    _tab_cal, _tab_dash, _tab_edit, _tab_log, _tab_diff, _tab_whatif = st.tabs(
        ["Календарь", "Нагрузка", "Редактирование", "Лог оптимизации", "Сравнение", "Что если?"]
    )

    with _tab_cal:
        _render_calendar(_schedule)
        render_employee_ics_downloads(_schedule)

    with _tab_dash:
        _render_load_dashboard(_schedule, _res["emp_df_snap"], _stats_list)

    edited_schedule_df: pd.DataFrame = _res["schedule_df"]
    with _tab_edit:
        st.caption(
            "Можно вручную изменить назначения. Имена сотрудников через запятую. "
            "Нажмите **Скачать XLS** — в файл попадёт актуальная версия таблицы."
        )
        edited_schedule_df = st.data_editor(
            _res["schedule_df"],
            column_config={
                "Дата": st.column_config.TextColumn("Дата", disabled=True, width="small"),
                "Утро 08–17": st.column_config.TextColumn("Утро 08–17", width="large"),
                "Вечер 15–00": st.column_config.TextColumn("Вечер 15–00", width="large"),
                "Ночь 00–08": st.column_config.TextColumn("Ночь 00–08", width="large"),
                "Рабочий день": st.column_config.TextColumn("Рабочий день", width="large"),
            },
            use_container_width=True,
            hide_index=True,
            key="schedule_editor",
        )

        _edit_schedule = _edit_df_to_schedule(edited_schedule_df, _schedule)
        _edit_violations = _validate_edited_schedule(_edit_schedule)
        if _edit_violations:
            with st.expander(f"Нарушения ({len(_edit_violations)})", expanded=True):
                for _v in _edit_violations:
                    st.warning(_v)
        else:
            st.success("Нарушений не обнаружено")

        if st.button("Пересчитать статистику", key="edit_recalc"):
            _edit_assign = build_assignments(_edit_schedule)
            _edit_stats = compute_stats(
                _edit_schedule, _edit_assign, _prod_days, short_days=_short_days
            )
            _edit_rows = []
            for _es in _edit_stats:
                _edit_rows.append(
                    {
                        "Сотрудник": _es.name,
                        "Раб.дней": _es.total_working,
                        "Норма": _es.target,
                        "Δ": _es.total_working - _es.target,
                        "Часы": _es.total_hours,
                        "Часы с надб.": _es.cost_hours,
                    }
                )
            st.dataframe(pd.DataFrame(_edit_rows), use_container_width=True, hide_index=True)

    _known_names = {e.name for e in _schedule.config.employees}
    _unknown_in_edit: set[str] = set()
    for _, _erow in edited_schedule_df.iterrows():
        for _ecol in ["Утро 08–17", "Вечер 15–00", "Ночь 00–08", "Рабочий день"]:
            _eval = str(_erow.get(_ecol, "")).strip()
            if _eval:
                for _ename in _eval.split(","):
                    _ename = _ename.strip()
                    if _ename and _ename not in _known_names:
                        _unknown_in_edit.add(_ename)
    if _unknown_in_edit:
        st.warning(
            f"Неизвестные имена в расписании: {', '.join(sorted(_unknown_in_edit))}. "
            "Проверьте правильность написания."
        )

    with _tab_log:
        _render_changelog(_schedule)

    with _tab_diff:
        _render_schedule_diff(_schedule)

    with _tab_whatif:
        _render_whatif_panel(
            _schedule,
            _res.get("holidays", set()),
            _res.get("short_days") or set(),
        )

    final_schedule = _edit_df_to_schedule(edited_schedule_df, _schedule)

    _xls_hash = _XLS_VERSION + str(pd.util.hash_pandas_object(edited_schedule_df).sum())
    if st.session_state.get("_xls_hash") != _xls_hash:
        with tempfile.TemporaryDirectory() as tmpdir:
            _sd = _res.get("short_days")
            xls_path = export_xls(final_schedule, Path(tmpdir), short_days=_sd)
            st.session_state["_xls_bytes"] = xls_path.read_bytes()
            st.session_state["_xls_hash"] = _xls_hash
    xls_bytes: bytes = st.session_state["_xls_bytes"]

    _dl_col1, _dl_col2 = st.columns(2)
    with _dl_col1:
        st.download_button(
            label="Скачать XLS",
            data=xls_bytes,
            file_name=f"schedule_{_res['gen_year']}_{_res['gen_month']:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    with _dl_col2:
        _pdf_hash = "pdf_" + _xls_hash
        _pdf_error = st.session_state.get("_pdf_error", False)
        if st.session_state.get("_pdf_hash") != _pdf_hash:
            _pdf_error = False
            try:
                _sd = _res.get("short_days")
                from duty_schedule.export.pdf import generate_schedule_pdf

                _pdf_bytes = generate_schedule_pdf(final_schedule, page_size="A3", short_days=_sd)
                st.session_state["_pdf_bytes"] = _pdf_bytes
            except (RuntimeError, OSError):
                _pdf_error = True
            st.session_state["_pdf_hash"] = _pdf_hash
            st.session_state["_pdf_error"] = _pdf_error
        if _pdf_error:
            st.warning("PDF недоступен: отсутствуют системные библиотеки WeasyPrint")
        else:
            st.download_button(
                label="Скачать PDF",
                data=st.session_state["_pdf_bytes"],
                file_name=f"schedule_{_res['gen_year']}_{_res['gen_month']:02d}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
    st.download_button(
        label=(f"Скачать конфиг для {MONTHS_RU[_res['next_month'] - 1]} {_res['next_year']}"),
        data=_res["next_yaml"].encode("utf-8"),
        file_name=f"config_{_res['next_year']}_{_res['next_month']:02d}.yaml",
        mime="text/yaml",
        use_container_width=True,
        help="Конфиг содержит состояния сотрудников на конец этого месяца.",
    )
