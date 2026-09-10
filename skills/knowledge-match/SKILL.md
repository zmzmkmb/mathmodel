---
name: knowledge-match
description: "数学建模题型、情景和知识库匹配专家。按逐题画像调用 Pro 案例、本地方法卡和规则验证层，并把结果反哺模型选择。"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, WebSearch, WebFetch
---

# 题型与知识库匹配

只负责画像、检索、候选路线和知识反哺。不要把历史案例直接复制成当前答案。

## 输入

优先读取：

- `analysis/problem_map.md`
- `data/data_dictionary.md`
- `data/semantic_mapping.md`
- `data/quality_report.md`
- `data/SOURCES.md`
- 当前问题已有报告和状态

对每个 `qN` 单独记录：

- 题型：预测、评价、优化、分类、统计、机理、仿真等，可多选；
- 机理、数据、优化成分 0-1；
- 情景标签：小样本、时间序列、缺失值、多目标、非线性等；
- 核心难点；
- 5-8 个真正的建模关键词；
- 置信度和待确认项。

## 三层检索

```powershell
python backend/scripts/search_knowledge.py `
  --task-types "<题型>" `
  --keywords "<建模关键词>" `
  --data-conditions "<数据条件>" `
  --core-difficulties "<核心难点>" `
  --scenario-tags "<情景标签>" `
  --top 6 `
  --format markdown
```

检索结果必须区分：

1. Pro 证据案例：历史方案、适用边界和避坑经验；
2. 本地方法卡：候选模型、求解和验证方法；
3. 规则与验证层：必须完成的推导、基线和红队测试。

当前后端是画像驱动的词项召回和情景加权，不应描述成向量嵌入意义上的深度语义相似度。

## 产物

- `analysis/knowledge_match_qN.md`

每条知识写清：为什么匹配、可迁移经验、不可迁移内容、对当前模型改了什么、仍有何风险。未命中 Pro 案例时必须明确写出。
