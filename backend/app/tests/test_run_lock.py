from app.core.workflow_state import acquire_run_lock, release_run_lock


def test_run_lock_is_exclusive_and_releasable(tmp_path):
    assert acquire_run_lock(tmp_path, "run-1") is True
    assert acquire_run_lock(tmp_path, "run-2") is False
    release_run_lock(tmp_path, "run-2")
    assert acquire_run_lock(tmp_path, "run-2") is False
    release_run_lock(tmp_path, "run-1")
    assert acquire_run_lock(tmp_path, "run-2") is True
