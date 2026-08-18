"""Pro 案例库适配与融合检索测试。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.knowledge.pro_cases import (
    build_pro_guidance_context,
    clear_pro_case_cache,
    load_pro_case_entries,
)
from app.core.knowledge.schemas import ModelingEntry, ModelUsage
from app.core.knowledge import store


CASE_CARD = """---
case_id: case-001
year: 2012
paper_code: A335
title: 葡萄酒质量评价
competition: CUMCM
problem_types: [评价, 回归]
models: [方差分析, 逐步回归]
keywords: [主观评分, 多指标评价]
validation_methods: [F检验, 拟合优度]
core_problem: 先校准主观评分，再完成质量评价。
data_features: 多评委重复评分与多源理化指标。
transferable_patterns: [先校准标签，再训练后续模型。]
source_page: https://example.com/case-001
evidence_mode: text
---

# 案例

- 【算法】评分校准后建立回归模型，并检查残差。
- 【模型选择理由】方差分析用于分离评委效应，回归用于解释质量。
- 【模型验证方法】比较处理前后的 F 统计量，并检查回归显著性。
- 【主要局限】小样本下逐步回归存在选择偏差。
- 【创新点】把评分可信度校准放在评价之前。
- 【可迁移经验】主观标签必须先做可靠性检验。
- 【不应该机械复制的部分】不能复制原论文的权重和回归系数。
- 【适用边界】单一评分者场景需要改用其他测量模型。
"""


def _local_entry() -> ModelingEntry:
    return ModelingEntry(
        id="2012_A335",
        source_paper="2012 CUMCM A335 本地提取",
        problem_type="综合评价",
        keywords=["葡萄酒", "评分"],
        context="本地知识条目",
        models=[ModelUsage(name="混合效应模型", role="评分校准", why="分离评委和样本效应")],
        solution_flow="先校准评分，再评价",
        validation="交叉验证",
        visualization=["评分箱线图"],
        pitfalls_avoided=["不把均值直接当真值"],
        innovation_points=[],
    )


class TestProKnowledge(unittest.TestCase):
    """验证外部案例解析、检索字段和重复论文融合。"""

    def tearDown(self) -> None:
        clear_pro_case_cache()
        store.load_evidence_case_kb.cache_clear()
        store.load_method_kb.cache_clear()
        store.load_searchable_modeling_kb.cache_clear()

    def test_load_pro_case_preserves_provenance(self) -> None:
        """案例卡应保留证据、迁移规律和适用边界。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cases_dir = Path(temp_dir) / "cases"
            cases_dir.mkdir()
            (cases_dir / "case-001.md").write_text(CASE_CARD, encoding="utf-8")

            with patch.dict(os.environ, {"MATHMODEL_PRO_KB_PATH": temp_dir}):
                clear_pro_case_cache()
                entries = load_pro_case_entries()

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.id, "pro:case-001")
        self.assertEqual(entry.paper_code, "A335")
        self.assertEqual(entry.evidence_mode, "text")
        self.assertIn("先校准标签", entry.transferable_patterns[0])
        self.assertTrue(entry.applicability_limits)
        self.assertNotIn("证据锚点", " ".join(entry.applicability_limits))
        self.assertEqual(entry.source_kind, "pro_case")

    def test_duplicate_paper_is_merged(self) -> None:
        """同一年份题号的本地条目和 Pro 卡片只保留一条融合结果。"""
        pro_entry = _local_entry().model_copy(
            update={
                "id": "pro:case-001",
                "year": 2012,
                "paper_code": "A335",
                "source_kind": "pro_case",
                "source_ids": ["case-001"],
                "transferable_patterns": ["先校准标签"],
                "source_page": "https://example.com/case-001",
            }
        )
        with (
            patch.object(store, "load_modeling_kb", return_value=[_local_entry()]),
            patch.object(store, "load_pro_case_entries", return_value=[pro_entry]),
        ):
            store.load_searchable_modeling_kb.cache_clear()
            entries = store.load_searchable_modeling_kb()

        self.assertEqual(len(entries), 1)
        merged = entries[0]
        self.assertEqual(merged.source_kind, "merged")
        self.assertIn("2012_A335", merged.source_ids)
        self.assertIn("case-001", merged.source_ids)
        self.assertIn("先校准标签", merged.transferable_patterns)

    def test_multi_search_keeps_pro_case(self) -> None:
        """多路检索应为 Pro 案例保留一个独立召回位置。"""
        pro_entry = _local_entry().model_copy(
            update={
                "id": "pro:case-001",
                "year": 2012,
                "paper_code": "A335",
                "source_kind": "pro_case",
            }
        )
        unrelated = _local_entry().model_copy(
            update={"id": "local-other", "source_paper": "本地其他案例"}
        )
        with (
            patch.object(store, "search_modeling", return_value=[unrelated]),
            patch.object(store, "search_pro_cases", return_value=[pro_entry]),
        ):
            entries, _ = store.search_modeling_multi(["评价"], ["评分"], max_total=4)

        self.assertTrue(any(entry.source_kind == "pro_case" for entry in entries))

    def test_layered_search_separates_evidence_and_methods(self) -> None:
        """分层检索应先返回 Pro 证据，再返回本地方法增强。"""
        pro_entry = _local_entry().model_copy(
            update={
                "id": "pro:case-001",
                "year": 2012,
                "paper_code": "A335",
                "source_kind": "pro_case",
            }
        )
        method_entry = _local_entry().model_copy(
            update={"id": "local-method", "source_paper": "本地方法卡"}
        )
        with (
            patch.object(store, "load_modeling_kb", return_value=[method_entry]),
            patch.object(store, "load_pro_case_entries", return_value=[pro_entry]),
        ):
            store.load_evidence_case_kb.cache_clear()
            store.load_method_kb.cache_clear()
            bundle = store.search_modeling_layers(["评价"], ["评分"], evidence_top=2, method_top=2)

        self.assertEqual(len(bundle.evidence_cases), 1)
        self.assertEqual(bundle.evidence_cases[0].source_kind, "pro_case")
        self.assertEqual(len(bundle.method_cards), 1)
        self.assertEqual(bundle.method_cards[0].source_kind, "local_method")
        self.assertTrue(bundle.validation_requirements)

    def test_guidance_context_reads_selected_documents(self) -> None:
        """专题知识文档应按任务类型作为有限长度上下文加入。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            knowledge_dir = Path(temp_dir) / "knowledge"
            knowledge_dir.mkdir()
            for name in ("problem-types.md", "model-selection.md", "validation-methods.md"):
                (knowledge_dir / name).write_text(f"# {name}\n测试知识内容", encoding="utf-8")

            with patch.dict(os.environ, {"MATHMODEL_PRO_KB_PATH": temp_dir}):
                context = build_pro_guidance_context(["优化"], max_chars=1800)

        self.assertIn("Pro 专题知识指南", context)
        self.assertIn("model-selection", context)


if __name__ == "__main__":
    unittest.main()
