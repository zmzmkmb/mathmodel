import sys
import types

sys.modules.setdefault("pypandoc", types.SimpleNamespace(convert_file=lambda *a, **k: None))
sys.modules.setdefault("e2b_code_interpreter", types.SimpleNamespace(AsyncSandbox=object))
sys.modules.setdefault(
    "ansi2html",
    types.SimpleNamespace(
        Ansi2HTMLConverter=type(
            "Ansi2HTMLConverter", (), {"convert": lambda self, text: text}
        )
    ),
)
sys.modules.setdefault("icecream", types.SimpleNamespace(ic=lambda *args, **kwargs: None))
sys.modules.setdefault("redis", types.ModuleType("redis"))
sys.modules.setdefault(
    "redis.asyncio",
    types.SimpleNamespace(Redis=types.SimpleNamespace(from_url=lambda *a, **k: None)),
)

from app.core.workflow import MathModelWorkFlow
from app.schemas.A2A import CoderToWriter, WriterResponse


def _workflow(tmp_path):
    workflow = MathModelWorkFlow()
    workflow.work_dir = str(tmp_path)
    workflow.task_id = "task-1"
    return workflow


def test_coder_checkpoint_requires_matching_plan_and_prompt(tmp_path):
    workflow = _workflow(tmp_path)
    response = CoderToWriter(
        success=True,
        executed_code=True,
        code_response="RMSE=0.2",
        code_output="validated output",
    )
    digest = workflow._checkpoint_digest("p1", "ques1", "prompt")
    workflow._save_coder_checkpoint("ques1", "p1", digest, response)

    loaded, summary = workflow._load_coder_checkpoint("ques1", "p1", digest)
    assert loaded is not None
    assert loaded.code_output == "validated output"
    assert summary
    assert workflow._load_coder_checkpoint("ques1", "p2", digest)[0] is None
    assert workflow._load_coder_checkpoint(
        "ques1", "p1", workflow._checkpoint_digest("p1", "ques1", "changed")
    )[0] is None


def test_invalid_coder_checkpoint_is_not_reused(tmp_path):
    workflow = _workflow(tmp_path)
    response = CoderToWriter(success=False, executed_code=True, code_response="failed")
    digest = workflow._checkpoint_digest("p1", "ques1", "prompt")
    workflow._save_coder_checkpoint("ques1", "p1", digest, response)
    assert workflow._load_coder_checkpoint("ques1", "p1", digest) == (None, None)


def test_writer_checkpoint_requires_matching_input(tmp_path):
    workflow = _workflow(tmp_path)
    response = WriterResponse(response_content="section")
    workflow._save_writer_checkpoint("writer_checkpoint", "ques1", "input-1", response)
    loaded = workflow._load_writer_checkpoint("writer_checkpoint", "ques1", "input-1")
    assert loaded is not None
    assert loaded.response_content == "section"
    assert workflow._load_writer_checkpoint("writer_checkpoint", "ques1", "input-2") is None
