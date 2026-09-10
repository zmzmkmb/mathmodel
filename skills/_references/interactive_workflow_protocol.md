# 交互式数学建模工作流协议

## 1. 两种运行模式

### 默认模式：局部交互

用户提出什么问题，就处理什么问题。先读取已有产物和 `workflow_state.json`，识别当前问题编号和任务类型，然后只调用相关 Skill。不得因为缺少后续阶段产物而强制启动完整流程。

### 完整执行模式

只有用户明确要求“完整执行”“从头跑一遍”“按全流程完成”时，才调用 `1start-mathmodel` 并按：

`初始化与恢复 -> 全局分析 -> 附件审计 -> 知识库匹配 -> 知识反哺 -> 逐题建模 -> 编码验证 -> 汇总分析 -> 流程图 -> 写作 -> 最终验收`

执行。

### 全流程审查模式

`full-review-officer` 是默认审查入口。它只读取和审查现有进度，输出缺口、风险和优先级，不自动重跑模型、不自动补齐所有阶段。

## 2. 语义路由

启动指令采用语义匹配，不要求用户记忆 Skill 名称：

| 用户意图 | 路由 |
| --- | --- |
| 审附件、查 Excel/CSV/PDF、查缺失和泄漏 | `data-auditor` |
| 判断题型、找类似案例、查方法和验证要求 | `knowledge-match` |
| 比较模型、写推导、检查假设和公式 | `model-workbench` |
| 写代码、复算、跑基线、红队测试 | `solve-and-validate` |
| 查结果是否自洽、论文数值是否一致 | `result-auditor` |
| 画流程图或技术路线图 | `4drawio` |
| 写论文某一节、改摘要或公式排版 | `5writing` |
| 完整检查当前项目 | `full-review-officer` |
| 明确要求完整执行 | `1start-mathmodel` |

用户可以直接说“审一下附件”“比较问题二模型”“补问题三公式”“复算问题一”“检查结果是否自洽”，路由器负责映射。

## 3. 软门禁

门禁分为三层，不把探索过程误判为最终失败：

- `DRAFT`：材料不足或仍在比较，不得作为最终结论。
- `WARN`：可以继续工作，但存在未解决风险，必须记录。
- `PASS`：证据充分，可以交给下一正式阶段或最终验收。

局部 Skill 可以在 `DRAFT/WARN` 下继续探索；只有 `model-workbench` 的正式推导和 `solve-and-validate` 的正式结果，才登记 `derivation_qN` 或 `validation_qN` 的最终门禁。

## 4. 上下文读取

所有局部 Skill 开始时读取：

- `workflow_state.json`（如果存在）
- `plan.md`、`todo.md`（如果存在）
- 当前问题相关的已有报告、代码和结果

建模相关 Skill 还必须优先读取：

- `analysis/problem_map.md`
- `analysis/knowledge_match_qN.md`
- `data/ingestion_manifest.md`
- `data/data_dictionary.md`
- `data/semantic_mapping.md`
- `data/quality_report.md`
- `data/cleaning_log.md`
- `data/SOURCES.md`

有多表连接或数据驱动预测时，再读取：

- `data/join_lineage.md`
- `data/split_leakage_audit.md`

缺失文件不应被伪造。应标记 `DRAFT` 或 `WARN`，并说明缺少什么。

## 5. 交接格式

局部 Skill 结束时输出：

```text
当前结论：
证据文件：
已完成产物：
门禁状态：DRAFT / WARN / PASS
未决问题：
建议下一动作：
```

除非用户明确要求，不自动调用“建议下一动作”对应的下一个 Skill。
