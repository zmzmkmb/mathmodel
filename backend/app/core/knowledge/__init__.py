"""知识库模块 —— 提供建模知识和写作知识的存储与检索。

四层知识库：
- evidence_cases: Pro 可追溯案例证据
- method_cards: 本地方法与实现增强
- rules_and_validation: 规则与验证要求
- writing_kb: 写作技法

快速使用：
    from app.core.knowledge.store import search_modeling, search_writing

    # 检索建模知识
    entries = search_modeling(problem_type="预测+优化", keywords=["热传导", "PDE"])

    # 检索写作技法
    tips = search_writing(section_type="摘要", keywords=["结构"])

    # 批量导入
    from app.core.knowledge.store import import_modeling_batch
    import_modeling_batch([entry1, entry2, ...])
"""

from app.core.knowledge.schemas import (
    ModelingEntry,
    ModelUsage,
    WritingEntry,
)
from app.core.knowledge.store import (
    load_modeling_kb,
    load_evidence_case_kb,
    load_method_kb,
    load_searchable_modeling_kb,
    load_searchable_modeling_kb_reload,
    load_writing_kb,
    search_modeling,
    search_modeling_layers,
    search_method_cards,
    search_modeling_multi,
    search_pro_cases,
    search_writing,
    append_modeling_entry,
    append_writing_entry,
    import_modeling_batch,
    import_writing_batch,
    build_modeling_context,
    build_modeling_context_from_profile,
    build_modeling_fallback_context,
    build_writing_context,
)
from app.core.knowledge.reader import DocumentReader, extract_papers

__all__ = [
    # schemas
    "ModelingEntry",
    "ModelUsage",
    "WritingEntry",
    # store
    "load_modeling_kb",
    "load_evidence_case_kb",
    "load_method_kb",
    "load_searchable_modeling_kb",
    "load_searchable_modeling_kb_reload",
    "load_writing_kb",
    "search_modeling",
    "search_modeling_layers",
    "search_method_cards",
    "search_modeling_multi",
    "search_pro_cases",
    "search_writing",
    "append_modeling_entry",
    "append_writing_entry",
    "import_modeling_batch",
    "import_writing_batch",
    "build_modeling_context",
    "build_modeling_context_from_profile",
    "build_modeling_fallback_context",
    "build_writing_context",
    # reader
    "DocumentReader",
    "extract_papers",
]
