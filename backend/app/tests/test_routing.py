"""软路由画像、验证组合和 CLI 契约测试。"""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from app.core.knowledge.routing import (
    build_validation_requirements,
    normalize_modeling_profile,
)


class TestSoftRouting(unittest.TestCase):
    """验证软画像不会退化为 B/C 硬分类。"""

    def test_normalize_route_keeps_overlapping_components(self) -> None:
        profile = normalize_modeling_profile({
            "task_types": ["预测", "优化"],
            "route_profiles": {
                "ques1": {
                    "mechanism": 0.4,
                    "data": 0.8,
                    "optimization": 0.7,
                    "confidence": "中",
                    "evidence": ["需要从历史数据预测", "预测结果进入资源配置"],
                }
            },
        })

        route = profile["route_profiles"]["ques1"]
        self.assertEqual(route["suggested_route"], "机理+数据+优化")
        self.assertTrue(route["revisable"])
        self.assertEqual(route["data"], 0.8)
        self.assertEqual(route["optimization"], 0.7)

    def test_validation_requirements_are_composed(self) -> None:
        requirements = build_validation_requirements({
            "task_types": ["预测", "优化"],
            "route_profiles": {
                "ques1": {"mechanism": 0.5, "data": 0.8, "optimization": 0.9}
            },
        })
        text = "\n".join(requirements)

        self.assertIn("硬门禁", text)
        self.assertIn("机理成分", text)
        self.assertIn("数据成分", text)
        self.assertIn("优化成分", text)
        self.assertIn("混合接口", text)

    def test_cli_profile_json_returns_layered_contract(self) -> None:
        """完整画像 CLI 应输出证据、方法和验证三个独立字段。"""
        from scripts.search_knowledge import main

        profile = json.dumps({
            "task_types": ["预测", "优化"],
            "search_keywords": ["时间序列", "调度"],
            "route_profiles": {
                "ques1": {"mechanism": 0.2, "data": 0.8, "optimization": 0.9}
            },
        }, ensure_ascii=False)
        stdout = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "search_knowledge.py",
                    "--profile-json",
                    profile,
                    "--top",
                    "6",
                    "--format",
                    "json",
                ],
            ),
            redirect_stdout(stdout),
        ):
            result = main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertIn("evidence_cases", payload)
        self.assertIn("method_cards", payload)
        self.assertIn("validation_requirements", payload)


if __name__ == "__main__":
    unittest.main()
