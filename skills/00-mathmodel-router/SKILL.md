---
name: 00-mathmodel-router
description: "数学建模交互式语义路由入口。根据用户当前意图选择局部 Skill；默认不强制推进全流程，明确要求完整执行时才调用 1start-mathmodel。"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, WebSearch, WebFetch
---

# 交互式数学建模语义路由

本 Skill 只负责识别当前请求、读取上下文并选择最小必要的专家 Skill。它不是总控流水线。

## 模式判断

先判断用户是否明确要求：

- “完整执行”“从头跑一遍”“按全流程完成”：进入 `full_execution`，调用 `1start-mathmodel`。
- “完整审查”“检查现在进度”“验收当前项目”：进入 `review`，调用 `full-review-officer`。
- 其他请求：进入 `interactive`，只调用与当前问题匹配的局部 Skill。

默认禁止因为用户提出局部问题而自动启动全流程。

## 语义匹配表

- 附件、Excel、CSV、PDF、缺失值、数据泄漏、字段含义：`data-auditor`
- 题型、建模关键词、历史案例、方法卡、验证方式：`knowledge-match`
- 候选模型、公式、假设、推导、六项检查、模型选择：`model-workbench`
- 代码、复算、基线、参数、随机种子、红队、图表：`solve-and-validate`
- 结果一致性、数值追溯、报告冲突、论文与代码不一致：`result-auditor`
- 技术路线图、模型结构图、非数据流程图：`4drawio`
- 摘要、章节、公式排版、Typst、LaTeX：`5writing`
- 全流程审查：`full-review-officer`
- 全流程执行：`1start-mathmodel`

## 路由步骤

1. 读取 `../_references/interactive_workflow_protocol.md`。
2. 读取项目根目录的 `workflow_state.json`、`plan.md`、`todo.md`（存在才读）。
3. 判断问题编号 `qN`，找不到时保持全局焦点，不要猜测。
4. 选择一个主 Skill；需要证据时可以先调用 `data-auditor` 或 `knowledge-match`，但不得无理由扩展任务范围。
5. 通过状态工具记录 `interactive` 模式和当前焦点。
6. 把已有产物路径、未决问题和门禁状态传给目标 Skill。

## 输出

路由前先说明：

```text
运行模式：interactive / full_execution / review
当前焦点：qN / 全局
主 Skill：<name>
读取证据：<paths>
```

路由后由目标 Skill 负责实际回答。除非用户明确要求继续，不自动执行下一个阶段。
