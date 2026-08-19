"""Persistence helpers for auditable workflow state transitions."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RESUMABLE_STATUSES = {"running", "failed"}
TERMINAL_STATUSES = {"completed", "skipped"}
RUN_LOCK_TTL_SECONDS = 6 * 60 * 60
TASK_REGISTRY_FILENAME = "task_registry.json"


def _task_registry_path(work_dir: str | Path) -> Path:
    return Path(work_dir) / TASK_REGISTRY_FILENAME


def load_task_registry(work_dir: str | Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(_task_registry_path(work_dir).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def update_task_registry(work_dir: str | Path, **updates: Any) -> dict[str, Any]:
    """Persist process-independent task metadata for status and cancellation."""
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    current = load_task_registry(root) or {}
    current.update(updates)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = _task_registry_path(root)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(current, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return current


def request_task_cancel(work_dir: str | Path) -> dict[str, Any]:
    return update_task_registry(work_dir, cancel_requested=True)


def is_task_cancel_requested(work_dir: str | Path) -> bool:
    registry = load_task_registry(work_dir)
    return bool(registry and registry.get("cancel_requested"))


def acquire_run_lock(work_dir: str | Path, run_id: str) -> bool:
    """Acquire a cross-process task lock using an atomic file create."""
    path = Path(work_dir) / "run.lock"
    payload = {"run_id": run_id, "pid": os.getpid(), "created_at": time.time()}
    try:
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if time.time() - float(existing.get("created_at", 0)) < RUN_LOCK_TTL_SECONDS:
                    return False
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
            path.unlink(missing_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        return True
    except FileExistsError:
        return False


def is_run_lock_active(work_dir: str | Path) -> bool:
    """Return whether the lock exists and has not exceeded its recovery TTL."""
    path = Path(work_dir) / "run.lock"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return time.time() - float(payload.get("created_at", 0)) < RUN_LOCK_TTL_SECONDS
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def release_run_lock(work_dir: str | Path, run_id: str) -> None:
    """Release the task lock only when it belongs to this run."""
    path = Path(work_dir) / "run.lock"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("run_id") == run_id:
            path.unlink(missing_ok=True)
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return


def append_state_event(
    work_dir: str | Path,
    task_id: str,
    stage: str,
    status: str,
    **extra: Any,
) -> dict[str, Any]:
    """Append one state transition and update the current-state snapshot."""
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    event = {
        "task_id": task_id,
        "stage": stage,
        "status": status,
        "updated_by": "MathModelWorkFlow",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    events_path = root / "workflow_events.json"
    try:
        events = json.loads(events_path.read_text(encoding="utf-8"))
        if not isinstance(events, list):
            events = []
    except (FileNotFoundError, json.JSONDecodeError):
        events = []
    events.append(event)
    events_path.write_text(
        json.dumps(events, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (root / "workflow_state.json").write_text(
        json.dumps(event, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return event


def load_workflow_state(work_dir: str | Path) -> dict[str, Any] | None:
    """Load the latest workflow snapshot, if a task has started."""
    path = Path(work_dir) / "workflow_state.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def get_resume_action(work_dir: str | Path) -> str:
    """Return a conservative action for a restarted task.

    This is intentionally advisory: executing a resumed task still requires
    the orchestration layer to decide whether its inputs and agents are ready.
    """
    state = load_workflow_state(work_dir)
    if state is None:
        return "start"
    status = state.get("status")
    if status in {"failed", "cancelled"}:
        return "retry_workflow"
    if status == "running":
        return "resume_stage"
    if status in TERMINAL_STATUSES:
        return "already_finished"
    return "inspect"
