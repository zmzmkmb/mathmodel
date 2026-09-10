---
name: solve-and-validate
description: "单问题编码、求解和验证专家。实现已选模型，运行基线、约束检查和至少三类红队测试，保存原始结果和图表。"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, WebSearch, WebFetch
---

# 编码、求解与验证

默认只处理一个 `qN`。兼容旧流程时可由 `3coding-visual` 调用，但不要求用户进入完整流程。

## 前置条件

读取：

- `analysis/problem_map.md`
- `analysis/derivations.md`
- `analysis/model_review_qN.md`
- `data/data_dictionary.md`
- `data/quality_report.md`
- `data/cleaning_log.md`
- `data/SOURCES.md`
- 相关 `analysis/knowledge_match_qN.md`

如果 `derivation_qN` 不是 `PASS`，可以做诊断性试算，但必须标记 `DRAFT/WARN`，不能登记正式验证通过。

## 每问任务

1. 读取数据并记录版本/哈希。
2. 实现批准的模型和算法。
3. 运行简单基线。
4. 检查约束、边界和不变量。
5. 保存参数、随机种子、环境和原始输出。
6. 生成与当前问题对应的数据图。
7. 至少执行三类红队测试：退化、极端/边界、噪声/缺失/对抗或求解器变化。
8. 记录失败、影响、修复和适用边界。

## 产物

- `code/problemN.py`
- `results/qN/`
- `reports/RESULTS_REPORT.md`
- `figures/` 中与结果直接相关的图表

每张图的代码必须打印关键数据特征，供写作阶段引用。

通过后登记：

```powershell
python backend/scripts/workflow_state.py gate --name validation_qN --status PASS --evidence "reports/RESULTS_REPORT.md#问题N"
python backend/scripts/workflow_state.py question --id qN --status completed --summary "核心结果、约束和红队证据已记录"
```

发现模型不适配时，回到 `model-workbench`；发现字段或连接问题时，回到 `data-auditor`，不要只在代码里静默绕过。
