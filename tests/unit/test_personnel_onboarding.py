import json

import pytest

from duty_schedule.models import City, ScheduleType
from duty_schedule.project import serialize_project
from duty_schedule.ui.onboarding import (
    OnboardingDraft,
    apply_city_lists,
    assign_roles,
    city_counts,
    complete_onboarding,
    draft_to_config,
    load_draft,
    serialize_draft,
)


def roster():
    return apply_city_lists(OnboardingDraft(year=2026, month=4), "M0\nM1\nM2\nM3", "K0\nK1")


def test_city_lists_preserve_names_and_reject_duplicates_atomically():
    original = OnboardingDraft(year=2026, month=4)
    result = apply_city_lists(original, "  Иванов, Иван  \n\n Пётр ", "")
    assert [e.name for e in result.employees] == ["Иванов, Иван", "Пётр"]
    assert all(e.city == City.MOSCOW for e in result.employees)
    assert all(e.schedule_type is None and e.on_duty is None for e in result.employees)
    assert original.employees == []
    for moscow, khabarovsk in [("", ""), ("Иван\n Иван ", ""), ("Иван", " Иван ")]:
        with pytest.raises(ValueError):
            apply_city_lists(result, moscow, khabarovsk)
    assert result.employees[0].name == "Иванов, Иван"


def test_reapplying_and_reordering_preserve_employee_ids():
    draft = roster()
    chosen = assign_roles(draft, [draft.employees[0].employee_id], ScheduleType.FIVE_TWO, False)
    again = apply_city_lists(chosen, "M3\nM2\nM1\nM0", "K1\nK0")
    assert {e.name: e.employee_id for e in again.employees} == {
        e.name: e.employee_id for e in draft.employees
    }
    assert again.employees[3].schedule_type == ScheduleType.FIVE_TWO
    assert again.employees[3].on_duty is False
    assert load_draft(serialize_draft(again)) == again


def test_partial_group_roles_and_independent_counts():
    draft = roster()
    ids = [e.employee_id for e in draft.employees]
    selected = assign_roles(draft, ids[:2], ScheduleType.FIVE_TWO, True)
    changed = assign_roles(selected, [ids[0]], None, False)
    assert changed.employees[0].schedule_type == ScheduleType.FIVE_TWO
    assert changed.employees[0].on_duty is False
    assert changed.employees[1].on_duty is True
    assert changed.employees[2].schedule_type is None
    assert city_counts(changed, City.MOSCOW) == {
        "total": 4,
        "five_two": 2,
        "flexible": 0,
        "on_duty": 1,
        "incomplete": 2,
    }
    with pytest.raises(ValueError):
        assign_roles(draft, ["unknown"], ScheduleType.FLEXIBLE, True)


def test_incomplete_roles_never_start_search(monkeypatch):
    from duty_schedule.ui import components

    def forbidden(*args, **kwargs):
        pytest.fail("Search must not run for onboarding")

    monkeypatch.setattr(components, "generate_schedule", forbidden)
    draft = roster()
    state = {"onboarding_draft": draft}
    with pytest.raises(ValueError, match="M0"):
        complete_onboarding(state)
    assert state == {"onboarding_draft": draft}
    partial = assign_roles(draft, [e.employee_id for e in draft.employees], ScheduleType.FLEXIBLE)
    with pytest.raises(ValueError, match="дежурств"):
        draft_to_config(partial)


def test_config_validation_remains_enforced():
    draft = roster()
    ids = [e.employee_id for e in draft.employees]
    invalid = assign_roles(draft, ids, ScheduleType.FLEXIBLE, False)
    state = {"onboarding_draft": invalid}
    with pytest.raises(ValueError, match="Недостаточно"):
        complete_onboarding(state)
    assert "project" not in state
    valid = assign_roles(invalid, ids, None, True)
    state["onboarding_draft"] = valid
    project = complete_onboarding(state)
    assert project.id == draft.id
    assert [e.employee_id for e in project.config.employees] == ids
    assert all(e.on_duty for e in project.config.employees)
    assert project.config.carry_over == []
    assert project.config.production_calendar is None


def test_invalid_import_preserves_draft_and_old_snapshots_restore():
    from duty_schedule.project import new_project
    from duty_schedule.ui.autosave import accept_storage_result
    from duty_schedule.ui.components import import_config_into_state, import_project_into_state
    from tests.ui.fixtures import journey_config

    draft = roster()
    state = {"onboarding_draft": draft, "autosave_token": "old"}
    for importer, raw in [(import_config_into_state, "{}"), (import_project_into_state, "{}")]:
        with pytest.raises(ValueError):
            importer(state, raw)
        assert state["onboarding_draft"] == draft
        assert "project" not in state
    project = new_project(journey_config())
    assert accept_storage_result(
        state, {"status": "restore", "project": serialize_project(project).decode(), "token": "new"}
    )
    assert serialize_project(state["project"]) == serialize_project(project)
    assert "onboarding_draft" not in state


@pytest.mark.parametrize(
    "change",
    [
        {"version": 9},
        {"kind": "unknown"},
        {"surprise": True},
        {"draft": {"year": 2026, "month": 13}},
    ],
)
def test_draft_envelope_rejects_unsupported_payloads(change):
    payload = json.loads(serialize_draft(roster()))
    payload.update(change)
    with pytest.raises(ValueError):
        load_draft(json.dumps(payload))


def test_rename_and_explicit_unset_preserve_identity():
    from duty_schedule.ui.onboarding import rename_personnel

    draft = roster()
    identity = draft.employees[0].employee_id
    configured = assign_roles(draft, [identity], ScheduleType.FIVE_TWO, True)
    renamed = rename_personnel(configured, identity, "Иванов, Иван")
    assert renamed.employees[0].employee_id == identity
    assert renamed.employees[0].on_duty is True
    assert renamed.employees[0].schedule_type == ScheduleType.FIVE_TWO
    for name in (" ", "M1", "Иван\nПётр"):
        with pytest.raises(ValueError):
            rename_personnel(renamed, identity, name)
    unset = assign_roles(renamed, [identity], None, False, replace=True)
    assert unset.employees[0].schedule_type is None
    assert unset.employees[0].on_duty is False
    assert unset.employees[0].employee_id == identity
    with pytest.raises(ValueError, match="график"):
        draft_to_config(unset)


def test_new_onboarding_has_separate_id_and_does_not_mutate_previous_project():
    from duty_schedule.project import new_project
    from duty_schedule.ui.onboarding import start_new_onboarding
    from tests.ui.fixtures import journey_config

    project = new_project(journey_config())
    before = serialize_project(project)
    state = {"project": project, "autosave_token": "confirmed", "autosave_status": "saved"}
    start_new_onboarding(state)
    assert state["onboarding_draft"].id != project.id
    assert state["onboarding_draft"].employees == []
    assert serialize_project(project) == before
    assert "project" not in state
    assert state["autosave_token"] is None
