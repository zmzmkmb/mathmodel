"""知识库数据模型 —— 建模知识库和写作知识库的结构定义。"""

from pydantic import BaseModel, Field


# ════════════════════════════════════════════
# 建模知识库
# ════════════════════════════════════════════

class ModelUsage(BaseModel):
    """单个模型的使用记录。"""
    name: str = Field(description="模型名称，如 ARIMA、XGBoost、NSGA-II")
    role: str = Field(description="在方案中的角色，如 '基线预测'、'多目标优化'")
    why: str = Field(description="选择理由，如 '数据量小(<15个)，灰色预测更适合'")


class ModelingEntry(BaseModel):
    """建模知识库的一条记录 —— 描述一篇优秀论文对一个问题的建模方案。"""

    id: str = Field(description="唯一标识，如 '2023-mcm-a-1st'")
    source_paper: str = Field(description="来源论文标题 + 获奖等级")
    problem_type: str = Field(
        description="问题类型分类，如 '预测+优化'、'综合评价'、'分类聚类'"
    )
    keywords: list[str] = Field(description="关键词，用于检索匹配")
    context: str = Field(description="问题背景简述（一句话）")

    models: list[ModelUsage] = Field(description="使用的模型列表及理由")
    solution_flow: str = Field(description="求解流程概述：数据→模型→参数→求解→验证")
    validation: str = Field(description="验证策略：用了什么指标、什么对比基线")

    visualization: list[str] = Field(description="可视化方案：用了哪些图表类型")
    pitfalls_avoided: list[str] = Field(description="避免的坑及原因")
    innovation_points: list[str] = Field(description="创新点（问题适配性创新，非算法复杂度创新）")

    # 外部案例库的可追溯字段。旧版 YAML 没有这些字段，均保持可选以兼容已有条目。
    year: int | None = Field(default=None, description="来源论文年份")
    paper_code: str | None = Field(default=None, description="赛题编号，如 A335")
    source_page: str | None = Field(default=None, description="可复核的来源页面")
    evidence_mode: str | None = Field(default=None, description="证据提取方式，如 text 或 ocr_sampled")
    data_features: str | None = Field(default=None, description="案例数据结构和约束特征")
    transferable_patterns: list[str] = Field(default_factory=list, description="可迁移的决策模式")
    applicability_limits: list[str] = Field(default_factory=list, description="不宜机械复用的边界")
    source_kind: str = Field(default="local", description="知识来源，如 local、pro_case 或 merged")
    source_ids: list[str] = Field(default_factory=list, description="合并前的原始条目 ID")


# ════════════════════════════════════════════
# 写作知识库
# ════════════════════════════════════════════

class WritingEntry(BaseModel):
    """写作知识库的一条记录 —— 描述优秀论文中某个段落的写作技法。"""

    id: str = Field(description="唯一标识，如 '2023-mcm-a-abstract'")
    source_paper: str = Field(description="来源论文标题 + 获奖等级")
    section_type: str = Field(
        description="章节类型，如 '摘要'、'问题分析'、'模型假设'、'敏感性分析'、'模型评价'"
    )
    keywords: list[str] = Field(description="关键词，用于检索匹配")

    technique: str = Field(description="此处运用的写作技法")
    excerpt: str = Field(description="范文片段摘录（关键句式、结构等）")
    why_effective: str = Field(description="为什么这样写有效（评委视角）")

    dos: list[str] = Field(default_factory=list, description="推荐写法")
    donts: list[str] = Field(default_factory=list, description="避免写法")
