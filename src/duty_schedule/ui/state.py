from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from duty_schedule.ui.mappings import (
    _DEFAULT_ROWS,
    _EMPTY_PIN_ROW,
)


def _init_state() -> None:
    if "table_version" not in st.session_state:
        st.session_state["table_version"] = 0
    if "employees_df" not in st.session_state:
        st.session_state["employees_df"] = pd.DataFrame(_DEFAULT_ROWS)
    if "cfg_month" not in st.session_state or "cfg_year" not in st.session_state:
        _today = date.today()
        _next_month = _today.month % 12 + 1
        _next_year = _today.year + (1 if _today.month == 12 else 0)
        if "cfg_month" not in st.session_state:
            st.session_state["cfg_month"] = _next_month
        if "cfg_year" not in st.session_state:
            st.session_state["cfg_year"] = _next_year
    if "cfg_seed" not in st.session_state:
        st.session_state["cfg_seed"] = 42
    if "pins_df" not in st.session_state:
        st.session_state["pins_df"] = pd.DataFrame([_EMPTY_PIN_ROW])
    if "carry_over" not in st.session_state:
        st.session_state["carry_over"] = []
    if "employee_dates" not in st.session_state:
        st.session_state["employee_dates"] = {}
    if "_df_for_download" not in st.session_state:
        st.session_state["_df_for_download"] = pd.DataFrame(_DEFAULT_ROWS)
    if "_pins_for_download" not in st.session_state:
        st.session_state["_pins_for_download"] = pd.DataFrame([_EMPTY_PIN_ROW])
    if "last_result" not in st.session_state:
        st.session_state["last_result"] = None


def _bump_table() -> None:
    old_ver = st.session_state["table_version"]
    st.session_state.pop(f"_gopt_{old_ver}", None)
    st.session_state["table_version"] = old_ver + 1


def _get_emp_dates(name: str) -> dict[str, Any]:
    ed: dict[str, dict[str, Any]] = st.session_state["employee_dates"]
    if name not in ed:
        ed[name] = {"vacations": [], "unavailable": [], "days_off_weekly": []}
    elif "days_off_weekly" not in ed[name]:
        ed[name]["days_off_weekly"] = []
    return ed[name]
