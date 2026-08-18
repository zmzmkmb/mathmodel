"""审计分层知识库的数量、重叠和来源完整度。"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.knowledge.store import (  # noqa: E402
    load_evidence_case_kb,
    load_method_kb,
    load_modeling_kb,
    load_searchable_modeling_kb,
)


def main() -> int:
    """输出机器可读的知识库分层审计结果。"""
    local = load_modeling_kb()
    evidence = load_evidence_case_kb()
    methods = load_method_kb()
    searchable = load_searchable_modeling_kb()
    source_kinds = Counter(entry.source_kind for entry in evidence)

    report = {
        "raw": {
            "local_entries": len(local),
            "pro_case_cards": len(evidence),
            "total_before_layering": len(local) + len(evidence),
        },
        "layered": {
            "evidence_cases": len(evidence),
            "method_cards": len(methods),
            "searchable_total": len(searchable),
            "evidence_enriched_by_local": source_kinds.get("merged", 0),
            "pure_pro_cases": source_kinds.get("pro_case", 0),
        },
        "provenance": {
            "evidence_with_source_page": sum(bool(entry.source_page) for entry in evidence),
            "evidence_with_evidence_mode": sum(bool(entry.evidence_mode) for entry in evidence),
            "evidence_with_limits": sum(bool(entry.applicability_limits) for entry in evidence),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
