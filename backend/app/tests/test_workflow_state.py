import json

from app.core.workflow_state import (
    append_state_event,
    is_task_cancel_requested,
    load_task_registry,
    request_task_cancel,
    update_task_registry,
)


def test_workflow_state_keeps_snapshot_and_history(tmp_path):
    append_state_event(tmp_path, "task-1", "modeler", "completed")
    append_state_event(tmp_path, "task-1", "coder", "failed", subtask="ques1")

    current = json.loads((tmp_path / "workflow_state.json").read_text())
    history = json.loads((tmp_path / "workflow_events.json").read_text())

    assert current["stage"] == "coder"
    assert current["status"] == "failed"
    assert len(history) == 2
    assert history[0]["stage"] == "modeler"
    assert history[1]["subtask"] == "ques1"


def test_task_registry_persists_cancel_request(tmp_path):
    update_task_registry(tmp_path, task_id="task-1", status="running", pid=123)
    assert load_task_registry(tmp_path)["status"] == "running"
    assert is_task_cancel_requested(tmp_path) is False
    request_task_cancel(tmp_path)
    assert is_task_cancel_requested(tmp_path) is True
