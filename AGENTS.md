# Repository Instructions

## Runtime Boundary

This repository uses a local Skills-first workflow. Do not add or restore FastAPI, Redis, WebSocket, frontend transport, A2A transport, E2B wrappers, OpenAlex agents, or an internal LLM factory unless the user explicitly requests a new architecture.

The supported runtime surface is:

- `skills/`
- `skills/_references/`
- `backend/app/core/knowledge/`
- `backend/scripts/`
- `backend/app/tests/`

## Python

- Python 3.12+
- Use `backend/.venv/Scripts/python.exe` on Windows.
- Keep CLIs local and filesystem-based.
- Use Google-style docstrings and `str | None` type syntax.
- Use UTF-8 for Chinese knowledge and protocol files.

## Validation

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest app.tests.test_pro_knowledge app.tests.test_routing app.tests.test_runtime_tools -v
.\.venv\Scripts\python.exe -m ruff check app/core/knowledge app/tests scripts
.\.venv\Scripts\python.exe -m compileall -q app/core/knowledge scripts
```

Do not revert unrelated user changes in this dirty worktree.
