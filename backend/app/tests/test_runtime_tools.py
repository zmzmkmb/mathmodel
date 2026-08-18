"""Skills-first 本地运行工具的契约测试。"""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import literature_registry, search_writing_knowledge, workflow_state


class TestWritingKnowledgeCli(unittest.TestCase):
    """验证章节检索会把题目关键词传给知识库。"""

    def test_markdown_search_forwards_keywords(self) -> None:
        stdout = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "search_writing_knowledge.py",
                    "--section-type",
                    "摘要",
                    "--keywords",
                    "预测,鲁棒性",
                    "--top",
                    "2",
                    "--format",
                    "markdown",
                ],
            ),
            patch.object(
                search_writing_knowledge,
                "build_writing_context",
                return_value="# 动态写作建议",
            ) as build_context,
            redirect_stdout(stdout),
        ):
            result = search_writing_knowledge.main()

        self.assertEqual(result, 0)
        self.assertIn("动态写作建议", stdout.getvalue())
        build_context.assert_called_once_with(
            "摘要",
            keywords=["预测", "鲁棒性"],
            top_k=2,
        )


class TestWorkflowStateCli(unittest.TestCase):
    """验证状态恢复、硬门禁和必需产物检查。"""

    def test_init_update_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "workflow_state.json"
            report = root / "reports" / "RESULTS_REPORT.md"
            report.parent.mkdir()
            report.write_text("# Results\n", encoding="utf-8")

            self.assertEqual(self._run("--path", str(state_path), "init"), 0)
            self.assertEqual(
                self._run(
                    "--path",
                    str(state_path),
                    "gate",
                    "--name",
                    "validation_q1",
                    "--status",
                    "PASS",
                    "--evidence",
                    "reports/RESULTS_REPORT.md",
                ),
                0,
            )
            self.assertEqual(
                self._run(
                    "--path",
                    str(state_path),
                    "artifact",
                    "--name",
                    "results_report",
                    "--file",
                    "reports/RESULTS_REPORT.md",
                    "--required",
                ),
                0,
            )
            self.assertEqual(
                self._run(
                    "--path",
                    str(state_path),
                    "validate",
                    "--root",
                    str(root),
                ),
                0,
            )

            state = workflow_state.load_state(state_path)
            self.assertEqual(state["gates"]["validation_q1"]["status"], "PASS")
            self.assertTrue(state["artifacts"]["results_report"]["required"])

    def test_fail_gate_and_open_error_are_rejected(self) -> None:
        state = workflow_state.new_state()
        state["gates"]["derivation_q1"] = {"status": "FAIL"}
        state["issues"].append({
            "id": "missing-source",
            "severity": "error",
            "status": "open",
        })

        errors = workflow_state.validate_state(state)

        self.assertTrue(any("derivation_q1" in error for error in errors))
        self.assertTrue(any("missing-source" in error for error in errors))

    @staticmethod
    def _run(*args: str) -> int:
        with patch.object(sys, "argv", ["workflow_state.py", *args]), redirect_stdout(io.StringIO()):
            return workflow_state.main()


class TestLiteratureRegistryCli(unittest.TestCase):
    """验证真实文献登记、核验门禁和双格式导出。"""

    def test_add_validate_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry_path = root / "data" / "literature.json"
            latex_path = root / "paper" / "references.tex"

            self.assertEqual(self._run("--path", str(registry_path), "init"), 0)
            self.assertEqual(
                self._run(
                    "--path",
                    str(registry_path),
                    "add",
                    "--id",
                    "ref1",
                    "--title",
                    "A Verified Modeling Paper",
                    "--authors",
                    "Author A;Author B",
                    "--year",
                    "2024",
                    "--venue",
                    "Journal of Modeling",
                    "--doi",
                    "10.1234/example.1",
                    "--verified-source",
                    "DOI landing page",
                    "--used-in",
                    "模型建立",
                    "--verification-status",
                    "verified",
                ),
                0,
            )
            self.assertEqual(self._run("--path", str(registry_path), "validate"), 0)
            self.assertEqual(
                self._run(
                    "--path",
                    str(registry_path),
                    "export",
                    "--format",
                    "latex",
                    "--output",
                    str(latex_path),
                ),
                0,
            )

            exported = latex_path.read_text(encoding="utf-8")
            self.assertIn("\\bibitem{ref1}", exported)
            self.assertIn("10.1234/example.1", exported)

    def test_unverified_and_duplicate_doi_are_rejected(self) -> None:
        registry = literature_registry.new_registry()
        base = {
            "title": "Paper",
            "authors": ["Author"],
            "year": 2024,
            "venue": "Venue",
            "doi": "10.1234/duplicate",
            "url": "",
            "verified_sources": [],
            "verification_status": "unverified",
            "used_in": ["引言"],
        }
        registry["references"] = [
            {"id": "ref1", **base},
            {"id": "ref2", **base},
        ]

        errors = literature_registry.validate_registry(registry)

        self.assertTrue(any("尚未核验" in error for error in errors))
        self.assertTrue(any("重复 DOI" in error for error in errors))

    @staticmethod
    def _run(*args: str) -> int:
        with patch.object(sys, "argv", ["literature_registry.py", *args]), redirect_stdout(io.StringIO()):
            return literature_registry.main()


if __name__ == "__main__":
    unittest.main()
