"""子问题软路由与验证要求生成。

路由只用于选择建模与验证工具，不是阻塞工作流的硬分类。真正的硬门禁是
数据可追溯、推导完整、实现一致和验证证据充分。
"""

from __future__ import annotations

from typing import Any


_SCORE_KEYS = {
    "mechanism": ("mechanism", "mechanism_score", "机理", "机理成分"),
    "data": ("data", "data_score", "数据", "数据成分"),
    "optimization": ("optimization", "optimization_score", "优化", "优化成分"),
}


def _as_list(value: Any) -> list[str]:
    """把模型输出中的标量或列表规范为非空字符串列表。"""
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _score(route: dict[str, Any], names: tuple[str, ...]) -> float:
    """读取并裁剪 0 到 1 的软路由分数。"""
    for name in names:
        if name not in route:
            continue
        try:
            return max(0.0, min(1.0, float(route[name])))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def normalize_modeling_profile(profile: Any) -> dict[str, Any]:
    """规范 Coordinator 画像，同时兼容旧版只有任务类型的输出。"""
    raw = profile if isinstance(profile, dict) else {}
    normalized: dict[str, Any] = {
        "task_types": _as_list(raw.get("task_types")),
        "search_keywords": _as_list(raw.get("search_keywords")),
        "data_conditions": _as_list(raw.get("data_conditions")),
        "core_difficulties": _as_list(raw.get("core_difficulties")),
        "route_profiles": {},
    }

    routes = raw.get("route_profiles") or raw.get("subproblem_routes") or {}
    if not isinstance(routes, dict):
        routes = {}

    for question, value in routes.items():
        route = value if isinstance(value, dict) else {}
        scores = {
            key: _score(route, aliases)
            for key, aliases in _SCORE_KEYS.items()
        }
        active = [
            label
            for key, label in (
                ("mechanism", "机理"),
                ("data", "数据"),
                ("optimization", "优化"),
            )
            if scores[key] >= 0.35
        ]
        suggested = str(
            route.get("suggested_route")
            or route.get("recommended_route")
            or "+".join(active)
            or "待推导后确认"
        ).strip()
        confidence = str(route.get("confidence") or "低").strip()
        if confidence not in {"低", "中", "高"}:
            confidence = "低"

        normalized["route_profiles"][str(question)] = {
            **scores,
            "suggested_route": suggested,
            "confidence": confidence,
            "evidence": _as_list(route.get("evidence")),
            "open_questions": _as_list(
                route.get("open_questions") or route.get("uncertainties")
            ),
            "revisable": bool(route.get("revisable", True)),
        }

    return normalized


def build_validation_requirements(profile: dict[str, Any]) -> list[str]:
    """依据软画像组合验证工具；分类本身不构成通过条件。"""
    normalized = normalize_modeling_profile(profile)
    routes = list(normalized["route_profiles"].values())
    task_text = " ".join(normalized["task_types"])

    mechanism = max((route["mechanism"] for route in routes), default=0.0)
    data = max((route["data"] for route in routes), default=0.0)
    optimization = max((route["optimization"] for route in routes), default=0.0)

    if any(token in task_text for token in ("机理", "仿真", "微分", "物理", "几何")):
        mechanism = max(mechanism, 0.5)
    if any(token in task_text for token in ("预测", "分类", "聚类", "评价", "统计", "回归")):
        data = max(data, 0.5)
    if any(token in task_text for token in ("优化", "调度", "规划", "决策")):
        optimization = max(optimization, 0.5)

    requirements = [
        "硬门禁：数据与参数可追溯，编码前有可求解推导，代码与推导一致，结论来自实际运行结果。",
        "通用验证：完成量纲、退化、不变量、边界与误差、适定性、反例六项检查，并执行至少三类红队测试。",
    ]
    if mechanism >= 0.25:
        requirements.append(
            "机理成分：检查守恒/不变量、边界与初始条件、退化极限、解的存在唯一性、收敛性或数值误差。"
        )
    if data >= 0.25:
        requirements.append(
            "数据成分：检查数据泄露、合理切分、简单基线、分层误差、校准/区间与样本扰动稳定性。"
        )
    if optimization >= 0.25:
        requirements.append(
            "优化成分：先验证可行域、变量物理上下界和约束满足，再比较目标值、基线求解器与收敛稳定性。"
        )
    if mechanism >= 0.25 and data >= 0.25:
        requirements.append(
            "混合接口：分别验证机理层和数据层，并追踪参数估计、代理模型或预测误差向决策结论的传播。"
        )
    return requirements
