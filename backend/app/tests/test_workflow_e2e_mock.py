import sys
import types
import asyncio

import pytest

from app.schemas.A2A import (
    CoderToWriter,
    CoordinatorToModeler,
    ModelerToCoder,
    WriterResponse,
)
from app.schemas.decision import (
    CandidatePlan,
    CaseEvidence,
    PanelOpinion,
    DecisionRecord,
)
from app.schemas.enums import CompTemplate, FormatOutPut
from app.schemas.request import Problem


class FakeRedis:
    async def publish_message(self, task_id, message):
        return None


class FakeInterpreter:
    def __init__(self):
        self.sections = []

    def add_section(self, name):
        self.sections.append(name)

    def get_code_output(self, name):
        return "validated output"

    async def get_created_images(self, name):
        return []

    async def cleanup(self):
        return None


class FakeUserOutput:
    def __init__(self, **kwargs):
        self.results = {}

    def set_res(self, key, value):
        self.results[key] = value

    def get_res(self):
        return self.results

    def get_model_build_solve(self):
        return "mock solution"

    def save_result(self):
        return None


class FakeFlows:
    def __init__(self, questions):
        self.questions = questions

    def get_solution_flows(self, questions, modeler_response):
        return {"ques1": {"coder_prompt": modeler_response.questions_solution["ques1"]}}

    def get_writer_prompt(self, key, coder_response, interpreter, config_template):
        return f"write {key}: {coder_response}"

    def get_write_flows(self, user_output, config_template, background):
        return {}


class FakeCoordinator:
    def __init__(self, *args, **kwargs):
        pass

    async def run(self, problem):
        return CoordinatorToModeler(questions={"background": problem, "ques1": "solve"}, ques_count=1)


class FakeModeler:
    def __init__(self, *args, **kwargs):
        pass

    async def run(self, coordinator):
        return ModelerToCoder(
            questions_solution={
                "_candidate_plans": [
                    CandidatePlan(
                        candidate_id="p1",
                        title="Initial",
                        description="initial plan",
                        solutions={"ques1": "initial code"},
                    ).model_dump(),
                ]
            }
        )


class FakeCaseEvidence:
    def __init__(self, *args, **kwargs):
        pass

    async def run(self, problem, coordinator, candidates, hits):
        return [
            CaseEvidence(
                candidate_id=candidate.candidate_id,
                match_status="none",
                evidence_summary="no matching case",
            )
            for candidate in candidates
        ]


class FakePanel:
    def __init__(self, *args, **kwargs):
        pass

    async def run(self, problem, candidates, evidence):
        revised = CandidatePlan(
            candidate_id="p2",
            title="Revised",
            description="revised plan after review",
            solutions={"ques1": "revised code"},
            source="panel",
        )
        return [
            PanelOpinion(
                candidate_id=candidates[0].candidate_id,
                verdict="revise",
                revised_plan=revised,
            )
        ]


class FakeChief:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def run(self, problem, candidates, evidence, panel, validation_feedback=None):
        type(self).calls += 1
        selected = "p1" if type(self).calls == 1 else "p2"
        plan = next(candidate for candidate in candidates if candidate.candidate_id == selected)
        return DecisionRecord(
            selected_candidate_id=selected,
            selected_plan=plan,
            decision_rationale="mock decision",
        )


class FakeCoder:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def run(self, prompt, subtask_title):
        type(self).calls += 1
        if type(self).calls == 1:
            return CoderToWriter(
                success=False,
                error_message="mock execution failure",
                attempts=3,
                executed_code=True,
            )
        return CoderToWriter(
            success=True,
            code_response="mock validated result",
            attempts=0,
            executed_code=True,
            created_images=[],
        )


class FakeWriter:
    def __init__(self, *args, **kwargs):
        pass

    async def run(self, *args, **kwargs):
        return WriterResponse(response_content="mock paper section")


def test_workflow_recovery_path_reaches_completed(tmp_path, monkeypatch):
    # Optional runtime packages are not needed for this fully mocked workflow.
    sys.modules.setdefault("pypandoc", types.SimpleNamespace(convert_file=lambda *a, **k: None))
    sys.modules.setdefault("e2b_code_interpreter", types.SimpleNamespace(AsyncSandbox=object))
    sys.modules.setdefault(
        "ansi2html",
        types.SimpleNamespace(
            Ansi2HTMLConverter=type(
                "Ansi2HTMLConverter",
                (),
                {"convert": lambda self, text: text},
            )
        ),
    )
    sys.modules.setdefault("icecream", types.SimpleNamespace(ic=lambda *args, **kwargs: None))
    redis_asyncio = types.SimpleNamespace(
        Redis=types.SimpleNamespace(from_url=lambda *a, **k: None)
    )
    sys.modules.setdefault("redis", types.ModuleType("redis"))
    sys.modules.setdefault("redis.asyncio", redis_asyncio)

    from app.core import workflow as workflow_module

    FakeChief.calls = 0
    FakeCoder.calls = 0
    monkeypatch.setattr(workflow_module, "CoordinatorAgent", FakeCoordinator)
    monkeypatch.setattr(workflow_module, "ModelerAgent", FakeModeler)
    monkeypatch.setattr(workflow_module, "CaseEvidenceAgent", FakeCaseEvidence)
    monkeypatch.setattr(workflow_module, "CasePanelAgent", FakePanel)
    monkeypatch.setattr(workflow_module, "ChiefPlannerAgent", FakeChief)
    monkeypatch.setattr(workflow_module, "CoderAgent", FakeCoder)
    monkeypatch.setattr(workflow_module, "WriterAgent", FakeWriter)
    monkeypatch.setattr(workflow_module, "Flows", FakeFlows)
    monkeypatch.setattr(workflow_module, "UserOutput", FakeUserOutput)
    monkeypatch.setattr(workflow_module, "create_work_dir", lambda task_id: str(tmp_path))
    monkeypatch.setattr(workflow_module, "create_interpreter", lambda **kwargs: None)
    monkeypatch.setattr(workflow_module, "redis_manager", FakeRedis())
    monkeypatch.setattr(workflow_module, "get_config_template", lambda template: {})
    monkeypatch.setattr(workflow_module, "LLMFactory", lambda task_id: types.SimpleNamespace(get_all_llms=lambda: (None, None, None, None)))
    monkeypatch.setattr(workflow_module, "LocalCaseLibrary", lambda path: types.SimpleNamespace(search=lambda query, limit: []))

    # create_interpreter is awaited by the workflow.
    async def fake_create_interpreter(**kwargs):
        return FakeInterpreter()

    monkeypatch.setattr(workflow_module, "create_interpreter", fake_create_interpreter)
    monkeypatch.setattr(workflow_module.settings, "COORDINATOR_MODEL", "mock")
    monkeypatch.setattr(workflow_module.settings, "MODELER_MODEL", "mock")
    monkeypatch.setattr(workflow_module.settings, "CODER_MODEL", "mock")
    monkeypatch.setattr(workflow_module.settings, "WRITER_MODEL", "mock")
    monkeypatch.setattr(workflow_module.settings, "COORDINATOR_API_KEY", "mock")
    monkeypatch.setattr(workflow_module.settings, "MODELER_API_KEY", "mock")
    monkeypatch.setattr(workflow_module.settings, "CODER_API_KEY", "mock")
    monkeypatch.setattr(workflow_module.settings, "WRITER_API_KEY", "mock")

    workflow = workflow_module.MathModelWorkFlow()
    problem = Problem(
        task_id="mock-task",
        ques_all="mock problem",
        comp_template=CompTemplate.CHINA,
        format_output=FormatOutPut.Markdown,
    )
    asyncio.run(workflow.execute(problem))

    import json

    state = json.loads((tmp_path / "workflow_state.json").read_text(encoding="utf-8"))
    events = json.loads((tmp_path / "workflow_events.json").read_text(encoding="utf-8"))
    stages = [(event["stage"], event["status"]) for event in events]

    assert state["stage"] == "completed"
    assert state["status"] == "completed"
    assert ("coder", "failed") in stages
    assert ("plan_selection", "completed") in stages
    assert stages[-1] == ("completed", "completed")
