"""维护可中断恢复的本地数学建模工作流状态。"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
STAGE_STATUSES = {"pending", "in_progress", "completed", "blocked"}
GATE_STATUSES = {"PASS", "WARN", "FAIL"}


def _now() -> str:
    """返回 UTC ISO 时间。"""
    return datetime.now(timezone.utc).isoformat()


def new_state() -> dict[str, Any]:
    """创建新的工作流状态。"""
    now = _now()
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "active",
        "current_stage": "initialized",
        "stages": {"initialized": {"status": "completed", "updated_at": now}},
        "questions": {},
        "gates": {},
        "artifacts": {},
        "issues": [],
        "created_at": now,
        "updated_at": now,
    }


def load_state(path: Path) -> dict[str, Any]:
    """读取状态文件。"""
    if not path.exists():
        raise FileNotFoundError(f"工作流状态不存在：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("workflow_state.json 顶层必须是对象")
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    """原子写入状态，避免中断留下半个 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        Path(temp_name).replace(path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def validate_state(state: dict[str, Any], root: Path | None = None) -> list[str]:
    """返回状态结构和硬门禁错误。"""
    errors: list[str] = []
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version 不受支持")
    if not isinstance(state.get("stages"), dict):
        errors.append("stages 必须是对象")
    else:
        for name, stage in state["stages"].items():
            if stage.get("status") not in STAGE_STATUSES:
                errors.append(f"阶段 {name} 状态无效")
    if not isinstance(state.get("gates"), dict):
        errors.append("gates 必须是对象")
    for name, gate in (state.get("gates") or {}).items():
        if gate.get("status") not in GATE_STATUSES:
            errors.append(f"门禁 {name} 状态无效")
        elif gate.get("status") == "FAIL":
            errors.append(f"门禁 {name} 尚未通过")
    for issue in state.get("issues") or []:
        if issue.get("severity") == "error" and issue.get("status") != "resolved":
            errors.append(f"错误问题尚未解决：{issue.get('id', 'unknown')}")
    if root is not None:
        for name, value in (state.get("artifacts") or {}).items():
            artifact = root / str(value.get("path", ""))
            if value.get("required") and not artifact.exists():
                errors.append(f"必需产物不存在：{name} -> {artifact}")
    return errors


def main() -> int:
    """执行状态更新子命令。"""
    parser = argparse.ArgumentParser(description="维护 workflow_state.json")
    parser.add_argument("--path", default="workflow_state.json", help="状态文件路径")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--force", action="store_true")

    stage_parser = subparsers.add_parser("stage")
    stage_parser.add_argument("--name", required=True)
    stage_parser.add_argument("--status", choices=sorted(STAGE_STATUSES), required=True)
    stage_parser.add_argument("--note", default="")

    question_parser = subparsers.add_parser("question")
    question_parser.add_argument("--id", required=True)
    question_parser.add_argument("--status", choices=sorted(STAGE_STATUSES), required=True)
    question_parser.add_argument("--summary", default="")

    gate_parser = subparsers.add_parser("gate")
    gate_parser.add_argument("--name", required=True)
    gate_parser.add_argument("--status", choices=sorted(GATE_STATUSES), required=True)
    gate_parser.add_argument("--evidence", default="")

    artifact_parser = subparsers.add_parser("artifact")
    artifact_parser.add_argument("--name", required=True)
    artifact_parser.add_argument("--file", required=True)
    artifact_parser.add_argument("--required", action="store_true")

    issue_parser = subparsers.add_parser("issue")
    issue_parser.add_argument("--id", required=True)
    issue_parser.add_argument("--severity", choices=("info", "warning", "error"), required=True)
    issue_parser.add_argument("--message", required=True)
    issue_parser.add_argument("--status", choices=("open", "resolved"), default="open")

    subparsers.add_parser("show")
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--root", default=".")

    args = parser.parse_args()
    path = Path(args.path)
    if args.command == "init":
        if path.exists() and not args.force:
            print(path.read_text(encoding="utf-8"), end="")
            return 0
        save_state(path, new_state())
        print(path)
        return 0

    state = load_state(path)
    now = _now()
    if args.command == "stage":
        state["current_stage"] = args.name
        state.setdefault("stages", {})[args.name] = {
            "status": args.status,
            "note": args.note,
            "updated_at": now,
        }
        if args.status == "completed" and args.name == "verify":
            state["status"] = "completed"
    elif args.command == "question":
        state.setdefault("questions", {})[args.id] = {
            "status": args.status,
            "summary": args.summary,
            "updated_at": now,
        }
    elif args.command == "gate":
        state.setdefault("gates", {})[args.name] = {
            "status": args.status,
            "evidence": args.evidence,
            "updated_at": now,
        }
    elif args.command == "artifact":
        state.setdefault("artifacts", {})[args.name] = {
            "path": args.file,
            "required": args.required,
            "updated_at": now,
        }
    elif args.command == "issue":
        issues = state.setdefault("issues", [])
        issues[:] = [issue for issue in issues if issue.get("id") != args.id]
        issues.append({
            "id": args.id,
            "severity": args.severity,
            "message": args.message,
            "status": args.status,
            "updated_at": now,
        })
    elif args.command == "show":
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    elif args.command == "validate":
        errors = validate_state(state, Path(args.root))
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 1 if errors else 0

    save_state(path, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
