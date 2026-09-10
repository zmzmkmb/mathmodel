# 本地工作流状态协议

`todo.md` 面向用户阅读，`workflow_state.json` 面向恢复、门禁和自动验收。两者必须同步，但状态文件是机器可读事实来源。

## 交互模式与当前焦点

工作流支持三种会话模式：

- `interactive`：默认模式。只处理用户当前请求，不强制推进后续阶段。
- `full_execution`：仅在用户明确要求“完整执行/从头跑一遍”时使用。
- `review`：由 `full-review-officer` 使用，只审查已有进度，不强制重跑。

状态文件新增以下字段；旧版状态缺少这些字段时按 `interactive` 和空焦点兼容读取：

```json
{
  "schema_version": 2,
  "session_mode": "interactive",
  "active_focus": {
    "problem": "q2",
    "task": "model_select",
    "request": "比较问题二候选模型",
    "updated_at": "2026-09-10T00:00:00+00:00"
  },
  "threads": {
    "q2": {
      "last_task": "model_select",
      "updated_at": "2026-09-10T00:00:00+00:00"
    }
  }
}
```

设置模式和焦点：

```bash
python "<项目根>/backend/scripts/workflow_state.py" mode --name interactive
python "<项目根>/backend/scripts/workflow_state.py" focus --problem q2 --task model_select --request "比较问题二候选模型"
python "<项目根>/backend/scripts/workflow_state.py" clear-focus
```

`current_stage` 仍保留用于兼容旧流程，但不再是交互路由的唯一依据。局部 Skill 可以在缺少前置材料时继续探索，但必须将状态标为 `DRAFT` 或 `WARN`，不能伪造最终 `PASS`。

## 工具

定位项目根目录下的脚本：

```bash
python "<项目根>/backend/scripts/workflow_state.py" --path workflow_state.json <command>
```

## 初始化

```bash
python "<项目根>/backend/scripts/workflow_state.py" init
```

已有状态时不要强制覆盖。恢复任务前先运行 `show`，读取当前阶段、问题状态、门禁、产物和未解决问题。

## 阶段更新

进入阶段：

```bash
python "<项目根>/backend/scripts/workflow_state.py" stage --name analysis --status in_progress
```

完成阶段：

```bash
python "<项目根>/backend/scripts/workflow_state.py" stage --name analysis --status completed --note "全局分析和软画像完成"
```

标准阶段名：`analysis`、`model_qN`、`code_qN`、`drawio`、`writing`、`verify`。

## 问题、门禁和产物

```bash
python "<项目根>/backend/scripts/workflow_state.py" question --id q1 --status completed --summary "最优目标值与验证结果已记录"
python "<项目根>/backend/scripts/workflow_state.py" gate --name derivation_q1 --status PASS --evidence "analysis/derivations.md#问题一"
python "<项目根>/backend/scripts/workflow_state.py" artifact --name results_report --file reports/RESULTS_REPORT.md --required
```

门禁只能使用 `PASS`、`WARN`、`FAIL`。存在 `FAIL` 时不得把相关阶段标为完成。

## 问题记录

```bash
python "<项目根>/backend/scripts/workflow_state.py" issue --id missing-source-q2 --severity error --message "参数 beta 缺少来源"
python "<项目根>/backend/scripts/workflow_state.py" issue --id missing-source-q2 --severity error --message "已补充来源" --status resolved
```

## 最终校验

```bash
python "<项目根>/backend/scripts/workflow_state.py" validate --root .
```

最终验收前必须通过状态结构和必需产物检查。状态文件不替代论文内容检查、编译或 PDF 视觉检查。
