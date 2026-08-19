from app.core.workflow_state import append_state_event, get_resume_action


def test_resume_action_is_derived_from_latest_snapshot(tmp_path):
    assert get_resume_action(tmp_path) == "start"

    append_state_event(tmp_path, "task-1", "coder", "failed")
    assert get_resume_action(tmp_path) == "retry_workflow"

    append_state_event(tmp_path, "task-1", "completed", "completed")
    assert get_resume_action(tmp_path) == "already_finished"
