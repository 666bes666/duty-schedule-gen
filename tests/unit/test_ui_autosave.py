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
