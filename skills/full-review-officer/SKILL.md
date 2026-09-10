---
name: full-review-officer
description: "数学建模全流程审查官。默认只审查现有进度，不强制重跑；明确要求完整执行时才转交 1start-mathmodel。"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, WebSearch, WebFetch
---

# 全流程审查官

## 两种模式

### 默认模式：审查现有进度

读取当前项目已有文件、状态和产物，检查流程完整性、证据链、模型与代码衔接、结果一致性、论文准备度和未决问题。默认不重跑代码、不重算模型、不自动补齐缺失阶段。

### 完整执行模式

只有用户明确要求完整执行时，才把任务转交给 `1start-mathmodel`。完整链路为：

`初始化与恢复 -> 全局题面分析 -> 附件数据审计 -> 题型与知识库匹配 -> 知识反哺模型 -> 逐题建模 -> 编码求解与验证 -> 汇总分析 -> 4drawio -> 5writing -> 6verity`

## 审查顺序

1. 读取 `../_references/interactive_workflow_protocol.md`、`workflow_gate_protocol.md`、`workflow_state_protocol.md`。
2. 读取 `workflow_state.json`、`plan.md`、`todo.md` 和已有报告。
3. 检查固定产物：
   - `analysis/problem_map.md`
   - `analysis/model_options_qN.md`
   - `analysis/derivations.md`
   - `analysis/model_review_qN.md`
   - `data/ingestion_manifest.md`
   - `data/data_dictionary.md`
   - `data/semantic_mapping.md`
   - `data/quality_report.md`
   - `data/cleaning_log.md`
   - `data/SOURCES.md`
   - `reports/ANALYSIS_MODELING_REPORT.md`
   - `reports/RESULTS_REPORT.md`
4. 按问题编号核对 `intake_qN`、`derivation_qN`、`validation_qN` 和实际文件。
5. 检查论文、图表、代码和结果之间的可追溯关系。
6. 把问题分为 `DRAFT`、`WARN`、`PASS`，给出优先级，不把缺失探索材料误报为恶意或最终失败。

## 输出

```markdown
# 全流程审查报告

## 总结
- 当前是否可继续工作：
- 当前最重要的三个缺口：

## 各问题状态
| 问题 | 建模 | 推导门 | 编码 | 验证 | 结论 |

## 证据链
题面/附件 -> 数据审计 -> 模型推导 -> 代码 -> 结果 -> 论文

## 风险与未决事项

## 建议的最小下一步
```

不因审查发现缺口而自动进入完整执行模式。用户明确说“完整跑一遍”后，才调用 `1start-mathmodel`。
