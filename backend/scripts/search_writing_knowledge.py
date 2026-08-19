"""按论文章节检索本地写作知识库。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.knowledge.store import build_writing_context, search_writing  # noqa: E402


def _csv(value: str) -> list[str]:
    """解析逗号分隔参数。"""
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    """检索指定章节的写作技法。"""
    parser = argparse.ArgumentParser(description="按章节检索数学建模写作知识")
    parser.add_argument("--section-type", required=True, help="章节类型，如 摘要、模型假设")
    parser.add_argument("--keywords", default="", help="补充关键词，逗号分隔")
    parser.add_argument("--top", type=int, default=3, help="最多返回条数")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    top = max(args.top, 1)
    keywords = _csv(args.keywords)
    if args.format == "markdown":
        context = build_writing_context(
            args.section_type,
            keywords=keywords,
            top_k=top,
        )
        if not context:
            print(f"未找到章节“{args.section_type}”的动态写作知识，请使用静态写作规范兜底。")
        else:
            print(context)
        return 0

    entries = search_writing(
        section_type=args.section_type,
        keywords=keywords,
        top_k=top,
    )
    print(json.dumps({
        "section_type": args.section_type,
        "entries": [entry.model_dump(mode="json") for entry in entries],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
