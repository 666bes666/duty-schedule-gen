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
    for name in (" ", "M1", "Иван\nПётр", "Иван\rПётр", "Иван\u2028Пётр"):
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


def test_native_personnel_operations_are_atomic_and_preserve_ids():
    from duty_schedule.ui.onboarding import add_personnel, remove_personnel, rename_personnel

    original = OnboardingDraft(year=2026, month=4)
    draft = add_personnel(original, City.MOSCOW, "  Иванов, Иван  ")
    assert draft.employees[0].name == "Иванов, Иван"
    identity = draft.employees[0].employee_id
    draft = assign_roles(draft, [identity], ScheduleType.FIVE_TWO, True)
    draft = add_personnel(draft, City.KHABAROVSK, "Пётр")
    assert draft.stage == "personnel"
    assert draft.employees[1].on_duty is None
    renamed = rename_personnel(draft, identity, "Иванов, Илья")
    assert renamed.employees[0].employee_id == identity
    assert renamed.employees[0].on_duty is True
    for name in ["", "  ", "Пётр", "Иван\nПётр", "Иван\rПётр"]:
        with pytest.raises(ValueError):
            add_personnel(renamed, City.MOSCOW, name)
    remaining = remove_personnel(renamed, renamed.employees[1].employee_id)
    assert len(remaining.employees) == 1
    assert remaining.employees[0] == renamed.employees[0]
    with pytest.raises(ValueError):
        remove_personnel(remaining, "unknown")
    empty = remove_personnel(remaining.model_copy(update={"stage": "roles"}), identity)
    assert empty.employees == []
    assert empty.stage == "personnel"
    assert original.employees == []
    assert load_draft(serialize_draft(remaining)) == remaining


def test_legacy_draft_without_stage_keeps_personnel_and_roles():
    draft = roster()
    draft = assign_roles(draft, [draft.employees[0].employee_id], ScheduleType.FIVE_TWO, True)
    raw = json.loads(serialize_draft(draft))
    raw["draft"].pop("stage")
    restored = load_draft(json.dumps(raw))
    assert restored.employees == draft.employees
    assert restored.stage == "personnel"
    raw["draft"]["employees"][0]["name"] = "Иван\rПётр"
    with pytest.raises(ValueError):
        load_draft(json.dumps(raw))


def test_pending_profiles_are_atomic_and_exclude_configured():
    from duty_schedule.ui.onboarding import assign_pending_roles, pending_personnel

    original = roster()
    ids = [e.employee_id for e in original.employees]
    partial = assign_pending_roles(original, ids[:2], ScheduleType.FIVE_TWO)
    assert len(pending_personnel(partial)) == 6
    configured = assign_pending_roles(partial, ids[:2], on_duty=True)
    assert [e.employee_id for e in pending_personnel(configured, City.MOSCOW)] == ids[2:4]
    before = serialize_draft(configured)
    for chosen in ([], [ids[0]], [ids[2], ids[0]], ["missing"]):
        with pytest.raises(ValueError, match="без полного назначения"):
            assign_pending_roles(configured, chosen, ScheduleType.FLEXIBLE, False)
        assert serialize_draft(configured) == before
    for schedule in ScheduleType:
        for duty in (True, False):
            changed = assign_pending_roles(original, ids, schedule, duty)
            assert not pending_personnel(changed)
            assert all(e.schedule_type == schedule and e.on_duty is duty for e in changed.employees)
            assert [e.employee_id for e in changed.employees] == ids
            assert load_draft(serialize_draft(changed)) == changed
