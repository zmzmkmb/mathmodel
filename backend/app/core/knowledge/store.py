"""知识库存储层 —— 文件系统读写 + jieba 分词检索 + 建模画像驱动多路检索。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache
from typing import Any

import yaml
import jieba

from .pro_cases import (
    build_pro_guidance_context,
    clear_pro_case_cache,
    load_pro_case_entries,
)
from .schemas import ModelingEntry, WritingEntry
from .routing import build_validation_requirements, normalize_modeling_profile

# ---- 配置 ----

KB_DIR = Path(__file__).resolve().parent / "data"

# ---- 底层文件 I/O ----

def _read_yaml(path: Path) -> list[dict]:
    """读取 YAML 文件，返回 dict 列表。文件不存在返回空列表。"""
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, list) else []


def _write_yaml(path: Path, data: list[dict]) -> None:
    """写入 YAML 文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


# =========================
# 建模知识库
# =========================

MODELING_KB_PATH = KB_DIR / "modeling.yaml"


def _build_modeling_index(entries: list[ModelingEntry]) -> dict[str, set[int]]:
    """构建倒排索引：关键词 → 匹配的条目索引集合。"""
    idx: dict[str, set[int]] = {}
    for i, entry in enumerate(entries):
        tokens = set(_tokenize(" ".join(entry.keywords) + " " + entry.problem_type))
        tokens.add(entry.problem_type.lower())
        for t in tokens:
            idx.setdefault(t, set()).add(i)
    return idx


@lru_cache(maxsize=1)
def load_modeling_kb(force_reload: bool = False) -> list[ModelingEntry]:
    """载入建模知识库全部条目。

    Args:
        force_reload: 仅用于兼容 lru_cache（python 位置参数）。传 True 无效，调用 load_modeling_kb.reload() 刷新。
    """
    data = _read_yaml(MODELING_KB_PATH)
    return [ModelingEntry(**d) for d in data]


def load_modeling_kb_reload() -> list[ModelingEntry]:
    """强制刷新并重新载入。"""
    load_modeling_kb.cache_clear()
    return load_modeling_kb()


def append_modeling_entry(entry: ModelingEntry) -> None:
    """追加一条建模条目并刷盘。"""
    data = _read_yaml(MODELING_KB_PATH)
    data.append(entry.model_dump())
    _write_yaml(MODELING_KB_PATH, data)
    load_modeling_kb.cache_clear()
    load_evidence_case_kb.cache_clear()
    load_method_kb.cache_clear()
    load_searchable_modeling_kb.cache_clear()


def _canonical_paper_key(entry: ModelingEntry) -> str:
    """为同一论文的不同知识条目生成稳定去重键。"""
    if entry.year and entry.paper_code:
        return f"paper:{entry.year}:{entry.paper_code.upper()}"
    match = re.search(
        r"(20\d{2})[_\s-]*([A-E]\d{3})",
        f"{entry.id} {entry.source_paper}",
        re.IGNORECASE,
    )
    if match:
        return f"paper:{match.group(1)}:{match.group(2).upper()}"
    return f"entry:{entry.id}"


def _unique_strings(*groups: list[str]) -> list[str]:
    """合并字符串列表并去除空值和重复项。"""
    return list(dict.fromkeys(item for group in groups for item in group if item))


def _merge_modeling_entries(first: ModelingEntry, second: ModelingEntry) -> ModelingEntry:
    """合并同一来源论文的本地与 Pro 条目，优先保留可追溯案例字段。"""
    pro_entry = first if first.source_kind == "pro_case" else second if second.source_kind == "pro_case" else first
    local_entry = second if pro_entry is first else first

    merged_models = list(local_entry.models)
    existing_model_names = {model.name.lower() for model in merged_models}
    merged_models.extend(model for model in pro_entry.models if model.name.lower() not in existing_model_names)

    data = pro_entry.model_dump()
    data.update(
        {
            "source_paper": pro_entry.source_paper or local_entry.source_paper,
            "problem_type": pro_entry.problem_type or local_entry.problem_type,
            "keywords": _unique_strings(pro_entry.keywords, local_entry.keywords),
            "context": pro_entry.context or local_entry.context,
            "models": merged_models,
            "solution_flow": pro_entry.solution_flow or local_entry.solution_flow,
            "validation": "；".join(_unique_strings([pro_entry.validation], [local_entry.validation])),
            "visualization": _unique_strings(pro_entry.visualization, local_entry.visualization),
            "pitfalls_avoided": _unique_strings(pro_entry.pitfalls_avoided, local_entry.pitfalls_avoided),
            "innovation_points": _unique_strings(pro_entry.innovation_points, local_entry.innovation_points),
            "transferable_patterns": _unique_strings(
                pro_entry.transferable_patterns, local_entry.transferable_patterns
            ),
            "applicability_limits": _unique_strings(
                pro_entry.applicability_limits, local_entry.applicability_limits
            ),
            "source_kind": "merged",
            "source_ids": _unique_strings(
                pro_entry.source_ids or [pro_entry.id], local_entry.source_ids or [local_entry.id]
            ),
        }
    )
    return ModelingEntry(**data)


@lru_cache(maxsize=1)
def load_evidence_case_kb() -> list[ModelingEntry]:
    """加载 Pro 证据案例，并用同源本地条目补充方法细节。"""
    local_by_key = {_canonical_paper_key(entry): entry for entry in load_modeling_kb()}
    evidence_cases: list[ModelingEntry] = []
    for pro_entry in load_pro_case_entries():
        local_entry = local_by_key.get(_canonical_paper_key(pro_entry))
        evidence_cases.append(
            _merge_modeling_entries(local_entry, pro_entry)
            if local_entry is not None
            else pro_entry
        )
    return evidence_cases


@lru_cache(maxsize=1)
def load_method_kb() -> list[ModelingEntry]:
    """加载未与 Pro 同源的本地条目，作为较低证据等级的方法卡。"""
    pro_keys = {_canonical_paper_key(entry) for entry in load_pro_case_entries()}
    return [
        entry.model_copy(
            update={
                "source_kind": "local_method",
                "source_ids": entry.source_ids or [entry.id],
            }
        )
        for entry in load_modeling_kb()
        if _canonical_paper_key(entry) not in pro_keys
    ]


@lru_cache(maxsize=1)
def load_searchable_modeling_kb() -> list[ModelingEntry]:
    """加载分层后的全部可检索知识：证据案例在前，方法卡在后。"""
    return [*load_evidence_case_kb(), *load_method_kb()]


def load_searchable_modeling_kb_reload() -> list[ModelingEntry]:
    """刷新本地与外部案例卡缓存后重新加载。"""
    load_modeling_kb.cache_clear()
    clear_pro_case_cache()
    load_evidence_case_kb.cache_clear()
    load_method_kb.cache_clear()
    load_searchable_modeling_kb.cache_clear()
    return load_searchable_modeling_kb()


# =========================
# 写作知识库
# =========================

WRITING_KB_PATH = KB_DIR / "writing.yaml"


def _build_writing_index(entries: list[WritingEntry]) -> dict[str, set[int]]:
    """构建倒排索引。"""
    idx: dict[str, set[int]] = {}
    for i, entry in enumerate(entries):
        tokens = set(_tokenize(" ".join(entry.keywords) + " " + entry.section_type))
        tokens.add(entry.section_type.lower())
        for t in tokens:
            idx.setdefault(t, set()).add(i)
    return idx


@lru_cache(maxsize=1)
def load_writing_kb(force_reload: bool = False) -> list[WritingEntry]:
    """载入写作知识库全部条目。"""
    data = _read_yaml(WRITING_KB_PATH)
    return [WritingEntry(**d) for d in data]


def load_writing_kb_reload() -> list[WritingEntry]:
    """强制刷新。"""
    load_writing_kb.cache_clear()
    return load_writing_kb()


def append_writing_entry(entry: WritingEntry) -> None:
    """追加一条写作条目并刷盘。"""
    data = _read_yaml(WRITING_KB_PATH)
    data.append(entry.model_dump())
    _write_yaml(WRITING_KB_PATH, data)
    load_writing_kb.cache_clear()


# =========================
# 检索
# =========================

def _tokenize(text: str) -> list[str]:
    """jieba 分词 + 英文单词提取，返回去重后的小写 token 列表。

    中文使用 jieba 搜索引擎模式（cut_for_search），将复合词拆为更细粒度；
    英文保留原正则提取，处理如 "ARIMA"、"XGBoost"、"R²" 等建模术语。
    """
    text = text.lower()
    tokens: list[str] = []

    # 英文单词/缩写（保留建模术语不被 jieba 误拆）
    tokens.extend(re.findall(r"[a-z0-9_]+", text))

    # 中文用 jieba 搜索引擎模式分词，过滤单字噪音
    chinese_chars = re.sub(r"[a-z0-9_\s]+", " ", text)
    chinese_chars = re.sub(r"\s+", " ", chinese_chars).strip()
    if chinese_chars:
        for w in jieba.cut_for_search(chinese_chars):
            w = w.strip()
            if w and len(w) >= 2:  # 过滤单字，减少噪音匹配
                tokens.append(w)

    return list(dict.fromkeys(tokens))  # 去重保序


def _search_by_tokens(
    query_tokens: set[str],
    entries: list[Any],
    *,
    problem_type: str = "",
    top_k: int = 5,
) -> list[int]:
    """通用词袋评分：对条目按 query_tokens 交集大小评分。

    Returns:
        按得分降序排列的条目索引列表。
    """
    scored: list[tuple[int, int]] = []  # (score, index)
    for i, entry in enumerate(entries):
        entry_text = " ".join(entry.keywords) + " " + getattr(entry, "problem_type", getattr(entry, "section_type", ""))
        entry_tokens = set(_tokenize(entry_text))
        score = len(query_tokens & entry_tokens)
        # problem_type / section_type 精确命中加分
        if problem_type:
            attr_val = getattr(entry, "problem_type", getattr(entry, "section_type", ""))
            if problem_type.lower() == attr_val.lower():
                score += 10
            elif problem_type.lower() in attr_val.lower():
                score += 5
        if score > 0:
            scored.append((score, i))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [idx for _, idx in scored[:top_k]]


def search_modeling(
    problem_type: str = "",
    keywords: list[str] | None = None,
    top_k: int = 5,
) -> list[ModelingEntry]:
    """检索建模知识库。

    Args:
        problem_type: 问题类型（如 '预测+优化'），精确匹配权重最高。
        keywords: 关键词列表，用于词袋匹配。
        top_k: 返回条数上限。

    Returns:
        按相关度降序排列的建模条目。
    """
    entries = load_searchable_modeling_kb()
    if not entries:
        return []

    # 构建查询 token 集合
    query_tokens: set[str] = set()
    if problem_type:
        query_tokens |= set(_tokenize(problem_type))
    if keywords:
        query_tokens |= set(_tokenize(" ".join(keywords)))

    if not query_tokens:
        return entries[:top_k]

    indices = _search_by_tokens(query_tokens, entries, problem_type=problem_type, top_k=top_k)
    return [entries[i] for i in indices]


def search_pro_cases(
    problem_type: str = "",
    keywords: list[str] | None = None,
    top_k: int = 3,
) -> list[ModelingEntry]:
    """检索 Pro 主证据案例，返回已融合的本地方法细节。"""
    entries = load_evidence_case_kb()
    if not entries:
        return []

    query_tokens: set[str] = set()
    if problem_type:
        query_tokens |= set(_tokenize(problem_type))
    if keywords:
        query_tokens |= set(_tokenize(" ".join(keywords)))
    if not query_tokens:
        return entries[:top_k]

    indices = _search_by_tokens(query_tokens, entries, problem_type=problem_type, top_k=top_k)
    return [entries[i] for i in indices]


def search_method_cards(
    problem_type: str = "",
    keywords: list[str] | None = None,
    top_k: int = 3,
) -> list[ModelingEntry]:
    """检索本地方法卡；这些条目用于补充方法，不作为最高等级来源证据。"""
    entries = load_method_kb()
    if not entries:
        return []

    query_tokens: set[str] = set()
    if problem_type:
        query_tokens |= set(_tokenize(problem_type))
    if keywords:
        query_tokens |= set(_tokenize(" ".join(keywords)))
    if not query_tokens:
        return entries[:top_k]

    indices = _search_by_tokens(
        query_tokens,
        entries,
        problem_type=problem_type,
        top_k=top_k,
    )
    return [entries[i] for i in indices]


def search_writing(
    section_type: str = "",
    keywords: list[str] | None = None,
    top_k: int = 5,
) -> list[WritingEntry]:
    """检索写作知识库。

    Args:
        section_type: 章节类型（如 '摘要'、'敏感性分析'）。
        keywords: 关键词列表。
        top_k: 返回条数上限。

    Returns:
        按相关度降序排列的写作条目。
    """
    entries = load_writing_kb()
    if not entries:
        return []

    query_tokens = set()
    if section_type:
        query_tokens |= set(_tokenize(section_type))
    if keywords:
        query_tokens |= set(_tokenize(" ".join(keywords)))

    if not query_tokens:
        return entries[:top_k]

    scored: list[tuple[int, WritingEntry]] = []
    for entry in entries:
        entry_tokens = set(_tokenize(" ".join(entry.keywords) + " " + entry.section_type))
        score = len(query_tokens & entry_tokens)
        if section_type and section_type in entry.section_type:
            score += 5
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]


# =========================
# 批量导入
# =========================

# =========================
# 知识上下文构建（供 Agent 注入）
# =========================


class _SearchStats:
    """内部检索统计，记录各路线的命中数。"""
    __slots__ = ("route1_count", "route2_count", "route3_count")

    def __init__(self, r1: int = 0, r2: int = 0, r3: int = 0):
        self.route1_count = r1
        self.route2_count = r2
        self.route3_count = r3


@dataclass(frozen=True)
class KnowledgeBundle:
    """一次分层检索的稳定返回契约。"""

    evidence_cases: list[ModelingEntry]
    method_cards: list[ModelingEntry]
    validation_requirements: list[str]
    guidance_context: str


def search_modeling_layers(
    task_types: list[str],
    keywords: list[str],
    *,
    data_conditions: list[str] | None = None,
    core_difficulties: list[str] | None = None,
    route_profiles: dict[str, Any] | None = None,
    evidence_top: int = 3,
    method_top: int = 3,
) -> KnowledgeBundle:
    """分别召回 Pro 证据案例和本地方法卡，并组合验证规则。"""
    expanded_keywords = _unique_strings(
        keywords,
        data_conditions or [],
        core_difficulties or [],
    )

    def collect(search_fn: Any, limit: int) -> list[ModelingEntry]:
        seen: set[str] = set()
        results: list[ModelingEntry] = []
        for task_type in task_types:
            for entry in search_fn(
                problem_type=task_type,
                keywords=expanded_keywords,
                top_k=max(1, limit),
            ):
                key = _canonical_paper_key(entry)
                if key not in seen:
                    seen.add(key)
                    results.append(entry)
                if len(results) >= limit:
                    return results
        if len(results) < limit:
            for entry in search_fn(keywords=expanded_keywords, top_k=limit):
                key = _canonical_paper_key(entry)
                if key not in seen:
                    seen.add(key)
                    results.append(entry)
                if len(results) >= limit:
                    break
        return results

    profile = normalize_modeling_profile({
        "task_types": task_types,
        "search_keywords": keywords,
        "data_conditions": data_conditions or [],
        "core_difficulties": core_difficulties or [],
        "route_profiles": route_profiles or {},
    })
    return KnowledgeBundle(
        evidence_cases=collect(search_pro_cases, evidence_top),
        method_cards=collect(search_method_cards, method_top),
        validation_requirements=build_validation_requirements(profile),
        guidance_context=build_pro_guidance_context(task_types),
    )


def search_modeling_multi(
    task_types: list[str],
    keywords: list[str],
    top_k_per_route: int = 3,
    max_total: int = 8,
) -> tuple[list[ModelingEntry], _SearchStats]:
    """兼容旧调用：把分层检索结果展平为证据案例在前的方法列表。

    Args:
        task_types: 问题任务类型列表，如 ['预测', '优化']。
        keywords: 从题目提取的关键词。
        top_k_per_route: 每路检索条数上限。
        max_total: 合并后的总条数上限。

    Returns:
        (去重后的建模条目列表, 路线统计)。
    """
    evidence_top = min(max(1, top_k_per_route), max_total)
    method_top = max(0, max_total - evidence_top)
    bundle = search_modeling_layers(
        task_types,
        keywords,
        evidence_top=evidence_top,
        method_top=method_top,
    )
    entries = [*bundle.evidence_cases, *bundle.method_cards][:max_total]
    return entries, _SearchStats(
        r1=len(bundle.evidence_cases),
        r2=len(bundle.method_cards),
        r3=len(bundle.validation_requirements),
    )


def _format_entry_as_decision_card(
    e: ModelingEntry,
    *,
    card_kind: str = "evidence",
) -> str:
    """将一条建模知识格式化为「决策依据卡片」而非论文摘要。

    重点展示：为什么选这些模型、避了什么坑、怎么验证的——
    让 Agent 做决策时有据可依，而不是照抄方案。
    """
    label = "证据案例" if card_kind == "evidence" else "方法卡"
    lines = [f"### [{label}] {e.problem_type} · {e.source_paper}"]
    if card_kind == "method":
        lines.append(
            "- **证据等级**: 本地方法增强；用于候选设计，不得仅凭该条目宣称模型优越或复用历史数值。"
        )
    lines.append("- **模型选择**:")
    for m in e.models[:8]:
        lines.append(f"  - {m.name}（{m.role}）：{m.why}")
    if len(e.models) > 8:
        lines.append(f"  - 其余 {len(e.models) - 8} 个模型请在进入详细建模时按需复核。")
    lines.append(f"- **求解路径**: {e.solution_flow}")
    lines.append(f"- **验证闭环**: {e.validation}")
    if e.pitfalls_avoided:
        lines.append(f"- **避坑**: {'; '.join(e.pitfalls_avoided[:3])}")
    if e.innovation_points:
        lines.append(f"- **创新点**: {'; '.join(e.innovation_points[:2])}")
    if e.transferable_patterns:
        lines.append(f"- **可迁移规律**: {'; '.join(e.transferable_patterns[:2])}")
    if e.applicability_limits:
        lines.append(f"- **适用边界**: {'; '.join(e.applicability_limits[:2])}")
    lines.append(f"- **可视化参考**: {', '.join(e.visualization[:4]) if e.visualization else '无'}")
    if e.source_page:
        evidence = f"，证据模式：{e.evidence_mode}" if e.evidence_mode else ""
        lines.append(f"- **来源复核**: {e.source_page}{evidence}")
    lines.append("")
    return "\n".join(lines)


def build_modeling_context(problem_text: str = "", top_k: int = 5) -> str:
    """旧版兼容接口：直接用文本分词检索。新代码应使用 build_modeling_context_from_profile。"""
    if not problem_text:
        entries = load_searchable_modeling_kb()[:top_k]
    else:
        entries = search_modeling(keywords=_tokenize(problem_text), top_k=top_k)
    if not entries:
        return ""

    lines = ["\n\n# 参考知识库（建模方案参考 · 请批判性使用，不要照搬）\n"]
    for e in entries:
        lines.append(_format_entry_as_decision_card(e))
    return "\n".join(lines)


def build_modeling_context_from_profile(
    task_types: list[str],
    keywords: list[str],
    data_conditions: list[str] | None = None,
    core_difficulties: list[str] | None = None,
    route_profiles: dict[str, Any] | None = None,
    max_total: int = 8,
) -> str:
    """从软画像构建分层上下文：证据案例、方法卡、验证规则。

    这是推荐入口——相比旧版 build_modeling_context（用原文直接搜），
    它先用 Coordinator 分析出的任务类型和关键词做结构化检索，返回的
    是决策依据卡片而非论文摘要，引导 Agent 论证而非照抄。

    Args:
        task_types: Coordinator 分析出的问题任务类型，如 ['预测', '优化', '综合评价']。
        keywords: Coordinator 提取的领域关键词，如 ['电池调度', '鲁棒优化', '选址']。
        max_total: 多路合并后返回的条目总数上限。

    Returns:
        格式化的建模上下文，无匹配时返回空字符串。
    """
    evidence_top = min(3, max(1, max_total))
    method_top = min(3, max(0, max_total - evidence_top))
    bundle = search_modeling_layers(
        task_types,
        keywords,
        data_conditions=data_conditions,
        core_difficulties=core_difficulties,
        route_profiles=route_profiles,
        evidence_top=evidence_top,
        method_top=method_top,
    )
    if not bundle.evidence_cases and not bundle.method_cards and not bundle.guidance_context:
        return ""

    lines = ["\n\n# 分层建模知识上下文\n"]
    lines.append(
        "> Pro 案例提供可追溯历史证据；本地方法卡补充模型与实现细节；软画像只选择验证工具，不是硬分类。\n"
    )
    if bundle.guidance_context:
        lines.append(bundle.guidance_context)
    if bundle.evidence_cases:
        lines.append(f"\n## 一、可追溯证据案例（{len(bundle.evidence_cases)}）\n")
        for entry in bundle.evidence_cases:
            lines.append(_format_entry_as_decision_card(entry, card_kind="evidence"))
    else:
        lines.append("\n## 一、可追溯证据案例\n\n未命中，不得用方法卡替代来源证据。\n")
    if bundle.method_cards:
        lines.append(f"\n## 二、本地方法增强卡（{len(bundle.method_cards)}）\n")
        for entry in bundle.method_cards:
            lines.append(_format_entry_as_decision_card(entry, card_kind="method"))
    lines.append("\n## 三、当前画像对应的验证要求\n")
    lines.extend(
        f"{index}. {requirement}"
        for index, requirement in enumerate(bundle.validation_requirements, start=1)
    )
    if not bundle.evidence_cases:
        lines.append("\n---\n")
        lines.append(build_modeling_fallback_context(task_types, keywords).lstrip("\n"))
    return "\n".join(lines)


def build_modeling_fallback_context(
    task_types: list[str] | None = None,
    keywords: list[str] | None = None,
) -> str:
    """知识库未命中时，构建「自检引导」上下文，提醒 Agent 以更高标准完成建模。

    与 build_modeling_context_from_profile 互补——当知识库找不到参考方案时，
    不是静默跳过，而是注入明确的约束和自检要求，防止 Agent 在无参考时降低质量。

    Args:
        task_types: Coordinator 分析出的问题任务类型，用于告知 Agent 问题结构。
        keywords: Coordinator 提取的领域关键词。

    Returns:
        自检引导文本。
    """
    lines = [
        "\n\n# ⚠️ 知识库未命中 —— 请以更高标准完成建模\n",
        "> 知识库中未找到与本问题高度匹配的参考方案。",
        "> 这可能是本问题具有新颖性，或题目场景不在已有知识覆盖范围内。",
        "> **你必须依赖建模经验和 prompt 中的决策指南，以更审慎的态度完成方案设计。**\n",
        "",
        "## 无知识库参考时的自检清单\n",
        "1. **模型选择论证**：对每个模型，明确写出：①为什么该模型适用于本问题 ②至少一个备选模型及不选它的理由 ③模型的适用条件（如线性假设、正态性等）本问题是否满足",
        "2. **验证策略必须具体**：禁止笼统写「用交叉验证」，必须写出具体方案（如 5 折时间序列交叉验证、留一法、Bootstrap N=1000 等）",
        "3. **参数设定必须有依据**：禁止写「根据经验设定」，必须给出推导过程或文献依据",
        "4. **可视化必须说明用途**：每张图必须说明「它验证了模型的哪个性质」",
        "5. **预判失败模式**：至少列出 2 个可能导致模型失效的场景，并说明应对策略",
        "6. **工程约束检查**（优化类必做）：每个优化变量必须有物理上界和下界，明确写出「无约束解为 XX，但因物理限制引入约束 XX≤XX_max」",
        "",
    ]
    if task_types:
        types_str = "、".join(task_types)
        lines.append(f"**本问题涉及的任务类型**: {types_str}")
    if keywords:
        kw_str = "、".join(keywords[:8])
        lines.append(f"**领域关键词**: {kw_str}")
    lines.append("")
    return "\n".join(lines)


def build_writing_context(
    section_type: str,
    keywords: list[str] | None = None,
    top_k: int = 3,
) -> str:
    """从知识库检索相关写作技法，构建可注入 prompt 的写作指南。

    Args:
        section_type: 章节类型（如 '摘要'、'敏感性分析'、'模型假设'）。
        keywords: 当前题目、模型或论证重点关键词。
        top_k: 检索条数。

    Returns:
        格式化的写作技法文本，无匹配时返回空字符串。
    """
    entries = search_writing(
        section_type=section_type,
        keywords=keywords,
        top_k=top_k,
    )
    if not entries:
        return ""

    lines = [f"\n\n# 参考写作技法（{section_type}部分）\n"]
    for e in entries:
        lines.append(f"**技法**: {e.technique}")
        lines.append(f"**范文片段**: {e.excerpt}")
        lines.append(f"**有效性**: {e.why_effective}")
        if e.dos:
            lines.append(f"**推荐**: {'; '.join(e.dos)}")
        if e.donts:
            lines.append(f"**避免**: {'; '.join(e.donts)}")
        lines.append("")
    return "\n".join(lines)


def import_modeling_batch(entries: list[ModelingEntry]) -> int:
    """批量导入建模条目（去重，按 id）。返回实际新增数量。"""
    existing = load_modeling_kb()
    existing_ids = {e.id for e in existing}
    new_entries = [e for e in entries if e.id not in existing_ids]
    if not new_entries:
        return 0

    data = _read_yaml(MODELING_KB_PATH)
    for e in new_entries:
        data.append(e.model_dump())
    _write_yaml(MODELING_KB_PATH, data)
    load_modeling_kb.cache_clear()
    return len(new_entries)


def import_writing_batch(entries: list[WritingEntry]) -> int:
    """批量导入写作条目（去重，按 id）。返回实际新增数量。"""
    existing = load_writing_kb()
    existing_ids = {e.id for e in existing}
    new_entries = [e for e in entries if e.id not in existing_ids]
    if not new_entries:
        return 0

    data = _read_yaml(WRITING_KB_PATH)
    for e in new_entries:
        data.append(e.model_dump())
    _write_yaml(WRITING_KB_PATH, data)
    load_writing_kb.cache_clear()
    return len(new_entries)
