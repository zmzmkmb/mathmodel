# MathModelAgent Local Skills Runtime

MathModelAgent 现在以本地 Skills-first 工作流运行，不再提供 FastAPI、Redis、WebSocket 或前端服务。

## 工作流

```text
1start-mathmodel
  -> 2analysis-modeling
  -> 3coding-visual
  -> 4drawio
  -> 5writing
  -> 6verity
```

`todo.md` 面向用户记录任务，`workflow_state.json` 保存机器可读阶段、门禁、产物和问题状态。

## 本地工具

```powershell
cd backend

# 建模知识检索
.\.venv\Scripts\python.exe scripts\search_knowledge.py --task-types "预测,优化" --keywords "时间序列,调度"

# 写作知识检索
.\.venv\Scripts\python.exe scripts\search_writing_knowledge.py --section-type "摘要" --keywords "预测,鲁棒性"

# 工作流状态
.\.venv\Scripts\python.exe scripts\workflow_state.py init
.\.venv\Scripts\python.exe scripts\workflow_state.py validate --root .

# 文献登记
.\.venv\Scripts\python.exe scripts\literature_registry.py init
.\.venv\Scripts\python.exe scripts\literature_registry.py validate
```

## 目录

```text
backend/app/core/knowledge/   本地分层知识库
backend/scripts/              检索、状态、文献和审计 CLI
backend/app/tests/            本地运行时测试
skills/                       六阶段建模工作流
skills/_references/           共享协议和知识参考
```

Web 搜索由当前 Agent Harness 提供；本地文献工具只负责登记、去重、核验和导出，不依赖旧 OpenAlex Agent。

## 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest app.tests.test_pro_knowledge app.tests.test_routing app.tests.test_runtime_tools -v
.\.venv\Scripts\python.exe -m ruff check app/core/knowledge app/tests scripts
.\.venv\Scripts\python.exe -m compileall -q app/core/knowledge scripts
```
