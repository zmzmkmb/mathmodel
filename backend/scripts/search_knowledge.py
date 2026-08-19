"""统一知识库检索 CLI，供 Skill 工作流和人工调试共用。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _csv(value: str) -> list[str]:
    """解析逗号分隔参数。"""
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    """执行建模知识库检索并输出 Markdown 或 JSON。"""
    parser = argparse.ArgumentParser(description="检索本地建模知识库和 math-modeling-skill-pro 案例库")
    parser.add_argument("--task-types", default="", help="任务类型，逗号分隔，如 预测,优化")
    parser.add_argument("--keywords", default="", help="建模关键词，逗号分隔")
    parser.add_argument("--data-conditions", default="", help="数据条件，逗号分隔")
    parser.add_argument("--core-difficulties", default="", help="核心难点，逗号分隔")
    parser.add_argument(
        "--profile-json",
        default="",
        help="完整软画像 JSON；提供时用于读取 route_profiles 等字段",
    )
    parser.add_argument("--problem-text", default="", help="没有画像时使用的题面文本")
    parser.add_argument("--top", type=int, default=6, help="最多返回条数")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--pro-kb-path", default="", help="Pro 仓库根目录，覆盖环境变量")
    args = parser.parse_args()

    if args.pro_kb_path:
        os.environ["MATHMODEL_PRO_KB_PATH"] = args.pro_kb_path

    from app.core.knowledge.store import (
        build_modeling_context,
        build_modeling_context_from_profile,
        search_modeling_layers,
    )

    task_types = _csv(args.task_types)
    keywords = _csv(args.keywords)
    data_conditions = _csv(args.data_conditions)
    core_difficulties = _csv(args.core_difficulties)
    route_profiles = {}
    if args.profile_json:
        profile = json.loads(args.profile_json)
        task_types = profile.get("task_types") or task_types
        keywords = profile.get("search_keywords") or keywords
        data_conditions = profile.get("data_conditions") or data_conditions
        core_difficulties = profile.get("core_difficulties") or core_difficulties
        route_profiles = profile.get("route_profiles") or {}
    if task_types or keywords:
        bundle = search_modeling_layers(
            task_types=task_types,
            keywords=keywords,
            data_conditions=data_conditions,
            core_difficulties=core_difficulties,
            route_profiles=route_profiles,
            evidence_top=min(3, max(args.top, 1)),
            method_top=min(3, max(0, args.top - 3)),
        )
        if args.format == "json":
            print(json.dumps({
                "evidence_cases": [
                    entry.model_dump(mode="json") for entry in bundle.evidence_cases
                ],
                "method_cards": [
                    entry.model_dump(mode="json") for entry in bundle.method_cards
                ],
                "validation_requirements": bundle.validation_requirements,
                "stats": {
                    "evidence_cases": len(bundle.evidence_cases),
                    "method_cards": len(bundle.method_cards),
                },
            }, ensure_ascii=False, indent=2))
        else:
            print(build_modeling_context_from_profile(
                task_types=task_types,
                keywords=keywords,
                data_conditions=data_conditions,
                core_difficulties=core_difficulties,
                route_profiles=route_profiles,
                max_total=max(args.top, 1),
            ))
        return 0

    if args.format == "markdown":
        print(build_modeling_context(args.problem_text, top_k=max(args.top, 1)))
    else:
        print(json.dumps({"context": build_modeling_context(args.problem_text, top_k=max(args.top, 1))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
