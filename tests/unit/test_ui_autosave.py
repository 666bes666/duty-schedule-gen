from duty_schedule.project import new_project, serialize_project
from tests.ui.fixtures import journey_config


def test_failed_and_corrupt_storage_preserve_valid_snapshot():
    from duty_schedule.ui.autosave import accept_storage_result

    project = new_project(journey_config())
    state = {"project": project, "autosave_token": "old"}
    for response in [
        {"status": "error", "error": "QuotaExceededError"},
        {"status": "restore", "project": "corrupt", "token": "new"},
        {"status": "conflict", "token": "new"},
    ]:
        accept_storage_result(state, response)
        assert serialize_project(state["project"]) == serialize_project(project)
        assert state["autosave_token"] == "old"
        assert state["autosave_status"] in ("error", "conflict")


def test_restore_revalidates_saved_ready():
    import json

    from duty_schedule.models import Schedule
    from duty_schedule.project import add_revision, current_schedule
    from duty_schedule.ui.autosave import accept_storage_result

    config = journey_config()
    project = add_revision(new_project(config), Schedule(config=config, days=[]))
    raw = json.loads(serialize_project(project))
    raw["revisions"][0]["schedule"]["status"] = "ready"
    state = {"project": new_project(config)}
    assert accept_storage_result(
        state, {"status": "restore", "project": json.dumps(raw), "token": "one"}
    )
    assert current_schedule(state["project"]).status == "diagnostic"


def test_draft_failure_conflict_and_transition_preserve_backup():
    import json

    from duty_schedule.models import ScheduleType
    from duty_schedule.ui.autosave import accept_storage_result
    from duty_schedule.ui.onboarding import (
        OnboardingDraft,
        apply_city_lists,
        assign_roles,
        complete_onboarding,
        serialize_draft,
        storage_snapshot,
    )

    draft = apply_city_lists(OnboardingDraft(year=2026, month=4), "M0\nM1\nM2\nM3", "K0\nK1")
    state = {"onboarding_draft": draft, "autosave_token": "old"}
    original = serialize_draft(draft)
    for response in [
        {"status": "error", "error": "QuotaExceededError"},
        {"status": "conflict", "token": "new"},
        {"status": "restore", "project": "corrupt", "token": "new"},
        {"status": "restore", "project": original},
    ]:
        assert not accept_storage_result(state, response)
        assert serialize_draft(state["onboarding_draft"]) == original
        assert state["autosave_token"] == "old"
    assert accept_storage_result(
        state, {"status": "restore", "project": original, "token": "confirmed"}
    )
    state["onboarding_draft"] = assign_roles(
        draft, [e.employee_id for e in draft.employees], ScheduleType.FLEXIBLE, True
    )
    complete_onboarding(state)
    snapshot, identity = storage_snapshot(state)
    assert identity == draft.id
    assert "kind" not in json.loads(snapshot)
    assert state["autosave_token"] == "confirmed"
    accept_storage_result(state, {"status": "error", "error": "QuotaExceededError"})
    assert state["onboarding_draft"].id == identity
    assert state["project"].id == identity
    assert state["autosave_token"] == "confirmed"
    assert accept_storage_result(
        state, {"status": "restore", "project": original, "token": "old-draft"}
    )
    assert "project" not in state
    assert serialize_draft(state["onboarding_draft"]) == original


def test_stale_hash_cannot_acknowledge_draft_or_project():
    from duty_schedule.ui.autosave import accept_storage_result
    from duty_schedule.ui.onboarding import OnboardingDraft

    state = {"onboarding_draft": OnboardingDraft(), "autosave_expected_hash": "latest"}
    assert not accept_storage_result(
        state, {"status": "saved", "hash": "stale", "token": "unexpected"}
    )
    assert "autosave_token" not in state
