"""读取 math-modeling-skill-pro 的结构化案例卡。

案例库以独立仓库存在，避免把受限来源的内容写入本项目的 YAML。运行时通过
``MATHMODEL_PRO_KB_PATH`` 指定路径；开发工作区中也会自动识别同级克隆目录。
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

from .schemas import ModelUsage, ModelingEntry

PRO_KB_ENV = "MATHMODEL_PRO_KB_PATH"
_CASE_SECTION_RE = re.compile(
    r"^- 【(?P<label>[^】]+)】(?P<value>.*?)(?=^- 【|^#{1,6}\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


def resolve_pro_kb_path(configured_path: str | Path | None = None) -> Path | None:
    """解析 Pro 案例库根目录，不存在时返回 ``None``。"""
    raw_path = str(configured_path or os.getenv(PRO_KB_ENV, "")).strip()
    if not raw_path:
        try:
            from app.config.setting import settings

            raw_path = str(getattr(settings, PRO_KB_ENV, "") or "").strip()
        except Exception:
            raw_path = ""

    if raw_path:
        candidate = Path(raw_path).expanduser()
    else:
        project_root = Path(__file__).resolve().parents[4]
        candidate = project_root.parent / "math-modeling-skill-pro"

    if candidate.name in {"cases", "knowledge"}:
        candidate = candidate.parent
    has_cases = (candidate / "cases").is_dir()
    has_knowledge = (candidate / "knowledge").is_dir()
    return candidate if has_cases or has_knowledge else None


def _read_frontmatter(path: Path) -> tuple[dict, str]:
    """读取 Markdown YAML front matter 与正文。"""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    metadata = yaml.safe_load(parts[1])
    return metadata if isinstance(metadata, dict) else {}, parts[2]


def _clean(value: str, limit: int = 900) -> str:
    """将案例正文压缩为适合 Prompt 的单行摘要。"""
    compact = re.sub(r"\s+", " ", value).strip(" -\n")
    return compact[:limit].rstrip()


def _sections(body: str) -> dict[str, str]:
    """提取案例卡中 ``【字段】`` 形式的决策字段。"""
    return {
        match.group("label"): _clean(match.group("value"))
        for match in _CASE_SECTION_RE.finditer(body)
    }


def _as_list(*values: str) -> list[str]:
    """过滤空值并保持顺序。"""
    return list(dict.fromkeys(value for value in values if value))


def _case_to_entry(metadata: dict, body: str) -> ModelingEntry | None:
    """将一张 Pro 案例卡转换为本项目可检索的建模条目。"""
    case_id = str(metadata.get("case_id", "")).strip()
    title = str(metadata.get("title", "")).strip()
    if not case_id or not title:
        return None

    sections = _sections(body)
    year = metadata.get("year")
    try:
        parsed_year = int(year) if year is not None else None
    except (TypeError, ValueError):
        parsed_year = None

    models = [
        ModelUsage(
            name=str(name),
            role="历史案例核心模型",
            why=sections.get("模型选择理由", "案例卡记录的核心方法；需按当前题的数据和约束重新论证。"),
        )
        for name in metadata.get("models", [])
        if str(name).strip()
    ]
    if not models:
        models = [
            ModelUsage(
                name="待从案例正文复核",
                role="历史案例参考",
                why="案例卡未提供可结构化模型列表，使用前需回看来源。",
            )
        ]

    validation_methods = [str(item) for item in metadata.get("validation_methods", []) if str(item).strip()]
    validation = "；".join(validation_methods)
    body_validation = sections.get("模型验证方法", "")
    if body_validation:
        validation = "；".join(_as_list(validation, body_validation))

    limitations = _as_list(
        sections.get("主要局限", ""),
        sections.get("不应该机械复制的部分", ""),
        sections.get("适用边界", ""),
    )
    transferable_patterns = [
        str(item) for item in metadata.get("transferable_patterns", []) if str(item).strip()
    ]
    transferable_patterns = _as_list(*transferable_patterns, sections.get("可迁移经验", ""))
    competition = str(metadata.get("competition", "CUMCM")).strip()
    paper_code = str(metadata.get("paper_code", "")).strip() or None
    source_label = " ".join(
        part for part in (str(parsed_year) if parsed_year else "", competition, paper_code or "", title) if part
    )

    return ModelingEntry(
        id=f"pro:{case_id}",
        source_paper=source_label,
        problem_type="+".join(str(item) for item in metadata.get("problem_types", []) if str(item).strip()) or "未分类",
        keywords=[str(item) for item in metadata.get("keywords", []) if str(item).strip()],
        context=str(metadata.get("core_problem", "")).strip() or sections.get("核心问题", title),
        models=models,
        solution_flow=sections.get("算法", "") or sections.get("决策链", "") or sections.get("问题拆解方式", ""),
        validation=validation or "案例卡未记录具体验证方法，需回看来源。",
        visualization=[],
        pitfalls_avoided=limitations,
        innovation_points=_as_list(sections.get("创新点", "")),
        year=parsed_year,
        paper_code=paper_code,
        source_page=str(metadata.get("source_page", "")).strip() or None,
        evidence_mode=str(metadata.get("evidence_mode", "")).strip() or None,
        data_features=str(metadata.get("data_features", "")).strip() or None,
        transferable_patterns=transferable_patterns,
        applicability_limits=limitations,
        source_kind="pro_case",
        source_ids=[case_id],
    )


@lru_cache(maxsize=4)
def load_pro_case_entries(configured_path: str = "") -> list[ModelingEntry]:
    """加载外部 Pro 案例卡；路径未配置或无效时返回空列表。"""
    root = resolve_pro_kb_path(configured_path or None)
    if root is None:
        return []

    entries: list[ModelingEntry] = []
    for card_path in sorted((root / "cases").glob("case-*.md")):
        metadata, body = _read_frontmatter(card_path)
        entry = _case_to_entry(metadata, body)
        if entry is not None:
            entries.append(entry)
    return entries


def clear_pro_case_cache() -> None:
    """刷新外部案例卡缓存，供配置变更或测试后调用。"""
    load_pro_case_entries.cache_clear()


def build_pro_guidance_context(task_types: list[str], max_chars: int = 7200) -> str:
    """按任务类型选取 Pro 专题知识文档，生成受限长度的指导上下文。"""
    root = resolve_pro_kb_path()
    if root is None:
        return ""

    selected = ["problem-types.md", "model-selection.md", "validation-methods.md"]
    task_text = " ".join(task_types)
    if any(token in task_text for token in ("预测", "回归", "分类", "聚类", "时间序列")):
        selected.extend(["data-workflow.md", "model-library.md"])
    if any(token in task_text for token in ("优化", "机理", "仿真", "网络")):
        selected.extend(["model-library.md", "model-combinations.md"])
    if "创新" in task_text:
        selected.append("innovation-patterns.md")

    selected = list(dict.fromkeys(selected))
    existing = [root / "knowledge" / name for name in selected]
    existing = [path for path in existing if path.is_file()]
    if not existing:
        return ""

    per_doc_limit = max(max_chars // len(existing), 600)
    lines = ["\n## Pro 专题知识指南（按需摘录，不能替代本题论证）\n"]
    for path in existing:
        content = _clean(path.read_text(encoding="utf-8"), limit=per_doc_limit)
        if content:
            lines.append(f"### {path.stem}\n{content}\n")
    return "\n".join(lines)
