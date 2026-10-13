from __future__ import annotations

import hashlib
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components

from duty_schedule.ui.onboarding import restore_snapshot, storage_snapshot

_bridge = components.declare_component(
    "duty_autosave", path=str(Path(__file__).with_name("autosave_component"))
)


def accept_storage_result(state: MutableMapping[Any, Any], response: dict) -> bool:
    status = response.get("status")
    if status == "restore":
        try:
            token = response["token"]
            if not isinstance(token, str):
                raise ValueError("Неверный token записи")
            restore_snapshot(state, response["project"])
        except (ValueError, KeyError, TypeError) as exc:
            state["autosave_status"] = "error"
            state["autosave_error"] = str(exc)
            return False
        state["autosave_token"] = token
        state["autosave_status"] = "error" if response.get("recovered") else "saved"
        if response.get("recovered"):
            state["autosave_error"] = (
                "Основная запись повреждена; восстановлена последняя резервная версия"
            )
        return True
    if status in ("error", "conflict"):
        state["autosave_status"] = status
        state["autosave_error"] = response.get("error", "Другая вкладка сохранила новую версию")
    elif status == "saved":
        if state.get("autosave_expected_hash") not in (None, response.get("hash")):
            return False
        state["autosave_token"] = response["token"]
        state["autosave_hash"] = response["hash"]
        state["autosave_status"] = "saved"
    elif status == "empty":
        state["autosave_status"] = "saving"
    return False


@st.fragment
def render_autosave() -> bool:
    state = st.session_state
    snapshot, identity = storage_snapshot(state)
    digest = hashlib.sha256(snapshot.encode()).hexdigest()
    state["autosave_expected_hash"] = digest
    phase = "write" if state.get("autosave_initialized") else "read"
    state.setdefault("autosave_writer", uuid4().hex)
    response = _bridge(
        phase=phase,
        project=snapshot,
        project_id=identity,
        expected_token=state.get("autosave_token"),
        hash=digest,
        writer=state["autosave_writer"],
        retry=state.get("autosave_retry", 0),
        blocked=state.get("autosave_status") in ("error", "conflict"),
        key="browser_autosave",
        default=None,
    )
    if response and response != state.get("autosave_response"):
        state["autosave_response"] = response
        restored = accept_storage_result(state, response)
        state["autosave_initialized"] = True
        if restored or phase == "read":
            st.rerun()
    if state.get("autosave_status") in ("error", "conflict"):
        st.error(
            f"Ошибка сохранения: {state.get('autosave_error')}. Открытый проект сохранён в памяти."
        )
        if st.button("Повторить сохранение"):
            state["autosave_status"] = "saving"
            state["autosave_retry"] = state.get("autosave_retry", 0) + 1
            st.rerun()
        if st.button("Сохранить копию в этом браузере"):
            key = (
                "roster_draft"
                if "roster_draft" in state
                else ("project" if "project" in state else "onboarding_draft")
            )
            identity = uuid4().hex
            state[key] = state[key].model_copy(update={"id": identity}, deep=True)
            if key == "roster_draft" and "project" in state:
                state["project"] = state["project"].model_copy(update={"id": identity}, deep=True)
            state["ui_epoch"] = int(state.get("ui_epoch", 0)) + 1
            state["autosave_token"] = None
            state["autosave_status"] = "saving"
            st.rerun()
        st.download_button(
            "Скачать резервный JSON",
            snapshot,
            file_name="schedule-backup.json",
            mime="application/json",
        )
    return bool(state.get("autosave_initialized"))
