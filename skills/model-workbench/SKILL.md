---
name: model-workbench
description: "单问题数学建模工作台。支持 select、derive、review 三种任务，充分调用知识库和数据审计产物，允许 DRAFT/WARN 探索，正式推导才登记软门禁 PASS。"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, WebSearch, WebFetch
---

# 单问题建模工作台

调用示例：

- `比较问题二模型` -> `select`
- `补问题三公式` -> `derive`
- `检查问题一假设` -> `review`

默认只处理指定的一个 `qN`，不自动处理全部问题。

## 前置读取

在 `select`、`derive` 或 `review` 前读取：

- `analysis/problem_map.md`
- `analysis/knowledge_match_qN.md`
- `data/ingestion_manifest.md`
- `data/data_dictionary.md`
- `data/semantic_mapping.md`
- `data/quality_report.md`
- `data/cleaning_log.md`
- `data/SOURCES.md`

存在多表连接或数据驱动预测时，读取：

- `data/join_lineage.md`
- `data/split_leakage_audit.md`

缺失时可以继续探索，但状态只能是 `DRAFT` 或 `WARN`，不得登记最终推导通过。

## select

比较 2-4 个候选模型，逐项说明：

- 题型和情景匹配；
- 数据条件；
- 物理/业务约束；
- 知识库依据；
- 不可迁移边界；
- 验证成本；
- 失败时的降级路线。

产物：`analysis/model_options_qN.md`。

## derive

正式写出：

- 符号、变量和参数来源；
- 目标函数或损失函数；
- 约束和边界条件；
- 求解器和停止条件；
- 输入、输出和可复现参数；
- 模型深度 L1/L2/L3；
- 六项检查：量纲、退化、不变量、边界与误差、适定性、反例。

产物：

- `analysis/derivations.md`
- `analysis/model_review_qN.md`
- 必要时更新 `reports/ANALYSIS_MODELING_REPORT.md`

只有可求解形式完整且没有未解释的 `FAIL`，才登记：

```powershell
python backend/scripts/workflow_state.py gate --name intake_qN --status PASS --evidence "analysis/problem_map.md#qN"
python backend/scripts/workflow_state.py gate --name derivation_qN --status PASS --evidence "analysis/derivations.md#问题N"
```

如果仍在比较或前置证据不足，登记 `WARN`，不要伪造 PASS。

## review

只审查当前模型和推导，列出：

- 已有证据；
- 缺失证据；
- 公式和代码的潜在冲突；
- 可接受的简化；
- 必须回到 `data-auditor` 或 `knowledge-match` 的问题。

## 语义交接

不自动调用编码 Skill。用户明确要求复算或实现时，才交给 `solve-and-validate`。
