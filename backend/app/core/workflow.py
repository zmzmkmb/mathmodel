"""工作流模块，编排多 Agent 协作完成数学建模任务。"""

import asyncio
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path

from app.core.agents import WriterAgent, CoderAgent, CoordinatorAgent, ModelerAgent
from app.core.agents.decision_agents import (
    CaseEvidenceAgent,
    CasePanelAgent,
    ChiefPlannerAgent,
)
from app.schemas.request import Problem
from app.schemas.response import SystemMessage
from app.tools.openalex_scholar import OpenAlexScholar
from app.utils.log_util import logger
from app.utils.common_utils import create_work_dir, get_config_template
from app.models.user_output import UserOutput
from app.config.setting import settings
from app.tools.interpreter_factory import create_interpreter
from app.services.redis_manager import redis_manager
from app.tools.notebook_serializer import NotebookSerializer
from app.tools.case_library import LocalCaseLibrary
from app.core.flows import Flows
from app.core.llm.llm_factory import LLMFactory
from app.schemas.A2A import CoderToWriter, CoordinatorToModeler, ModelerToCoder, WriterResponse
from app.schemas.decision import CandidatePlan, CaseEvidence, DecisionRecord, PanelOpinion
from app.core.candidate_plans import normalize_candidates
from app.core.workflow_state import append_state_event, is_task_cancel_requested
from app.core.validation import validate_coder_response


class WorkFlow:
    """工作流基类。"""

    def __init__(self):
        pass

    def execute(self) -> None:
        """执行工作流。"""
        # RichPrinter.workflow_start()
        # RichPrinter.workflow_end()
        pass


class MathModelWorkFlow(WorkFlow):
    """数学建模工作流，协调协调者、建模手、代码手和写作手完成完整建模任务。"""
    task_id: str  #
    work_dir: str  # worklow work dir
    ques_count: int = 0  # 问题数量
    questions: dict[str, str | int] = {}  # 问题
    cancel_event: asyncio.Event | None = None  # 取消信号
    run_id: str | None = None

    def _prepare_work_dir(self, task_id: str, run_id: str | None) -> str:
        """Use the legacy task directory once, then isolate recovery runs."""
        base = Path(create_work_dir(task_id))
        previous_work_dir = None
        current_run_path = base / "current_run.json"
        if run_id is not None and current_run_path.exists():
            try:
                previous_work_dir = Path(json.loads(current_run_path.read_text(encoding="utf-8")).get("work_dir", ""))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                previous_work_dir = None
        self.run_id = run_id or "initial"
        if run_id is None:
            work_dir = base
        else:
            work_dir = base / "runs" / run_id
            work_dir.mkdir(parents=True, exist_ok=True)
            excluded = {
                "problem.json",
                "workflow_state.json",
                "workflow_events.json",
                "current_run.json",
                "res.json",
                "res.md",
                "res.docx",
                "notebook.ipynb",
            }
            for source in base.iterdir():
                if source.name in excluded or source.name == "runs":
                    continue
                if source.is_file():
                    shutil.copy2(source, work_dir / source.name)
            # Recovery runs inherit structured checkpoints from the immediately
            # preceding run, while keeping state history and outputs isolated.
            if previous_work_dir and previous_work_dir.is_dir():
                for source in previous_work_dir.iterdir():
                    if source.is_file() and source.name not in excluded and source.name != "run.lock":
                        shutil.copy2(source, work_dir / source.name)
        (base / "current_run.json").write_text(
            json.dumps(
                {"task_id": task_id, "run_id": self.run_id, "work_dir": str(work_dir)},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return str(work_dir)

    def _write_json(self, filename: str, payload: object) -> None:
        """Persist an auditable intermediate artifact for this task."""
        path = Path(self.work_dir) / filename
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _read_json(self, filename: str) -> object | None:
        try:
            return json.loads((Path(self.work_dir) / filename).read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _checkpoint_digest(*parts: object) -> str:
        payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _checkpoint_suffix(subtask: str) -> str:
        readable = re.sub(r"[^A-Za-z0-9_.-]+", "_", subtask).strip("._")[:40]
        digest = hashlib.sha256(subtask.encode("utf-8")).hexdigest()[:12]
        return f"{readable or 'subtask'}_{digest}"

    def _checkpoint_file(self, kind: str, subtask: str) -> str:
        return f"{kind}_{self._checkpoint_suffix(subtask)}.json"

    def _load_coder_checkpoint(
        self, subtask: str, candidate_id: str, prompt_digest: str
    ) -> tuple[CoderToWriter | None, str | None]:
        payload = self._read_json(self._checkpoint_file("coder_checkpoint", subtask))
        if not isinstance(payload, dict):
            return None, None
        if payload.get("candidate_id") != candidate_id or payload.get("prompt_digest") != prompt_digest:
            return None, None
        try:
            response = CoderToWriter.model_validate(payload["response"])
        except (KeyError, TypeError, ValueError):
            return None, None
        valid, summary = validate_coder_response(response)
        if not valid:
            return None, None
        return response, summary

    def _save_coder_checkpoint(
        self,
        subtask: str,
        candidate_id: str,
        prompt_digest: str,
        response: CoderToWriter,
    ) -> None:
        self._write_json(
            self._checkpoint_file("coder_checkpoint", subtask),
            {
                "subtask": subtask,
                "candidate_id": candidate_id,
                "prompt_digest": prompt_digest,
                "response": response.model_dump(),
            },
        )

    def _restore_coder_output(self, code_interpreter: object, subtask: str, response: CoderToWriter) -> None:
        """Rehydrate the minimal interpreter section needed by Writer prompts."""
        code_output = response.code_output
        if code_output and hasattr(code_interpreter, "add_content"):
            code_interpreter.add_content(subtask, code_output)

    def _load_writer_checkpoint(
        self, kind: str, subtask: str, input_digest: str
    ) -> WriterResponse | None:
        payload = self._read_json(self._checkpoint_file(kind, subtask))
        if not isinstance(payload, dict) or payload.get("input_digest") != input_digest:
            return None
        try:
            response = WriterResponse.model_validate(payload["response"])
        except (KeyError, TypeError, ValueError):
            return None
        if not str(response.response_content or "").strip():
            return None
        return response

    def _save_writer_checkpoint(
        self, kind: str, subtask: str, input_digest: str, response: WriterResponse
    ) -> None:
        self._write_json(
            self._checkpoint_file(kind, subtask),
            {
                "subtask": subtask,
                "input_digest": input_digest,
                "response": response.model_dump(),
            },
        )

    def _write_state(self, stage: str, status: str, **extra: object) -> None:
        """Persist the current checkpoint and append an audit event."""
        append_state_event(
            self.work_dir,
            self.task_id,
            stage,
            status,
            **extra,
        )

    @staticmethod
    def _normalize_candidates(modeler_response: ModelerToCoder) -> list[CandidatePlan]:
        return normalize_candidates(modeler_response)

    @staticmethod
    def _apply_panel_revisions(
        candidates: list[CandidatePlan], opinions: list[object]
    ) -> list[CandidatePlan]:
        """Merge Panel-created plans into the candidate set for Chief review."""
        merged = {candidate.candidate_id: candidate for candidate in candidates}
        original_ids = set(merged)
        for opinion in opinions:
            revised_plan = getattr(opinion, "revised_plan", None)
            verdict = getattr(opinion, "verdict", None)
            if verdict == "revise" and revised_plan is None:
                raise ValueError(
                    f"Panel opinion for {getattr(opinion, 'candidate_id', '')} "
                    "requires revised_plan"
                )
            if revised_plan is not None:
                if revised_plan.candidate_id in original_ids:
                    existing_plan = merged[revised_plan.candidate_id]
                    if existing_plan != revised_plan:
                        raise ValueError(
                            "Panel revised_plan reuses candidate_id with different content"
                        )
                    continue
                source_candidate = merged.get(getattr(opinion, "candidate_id", ""))
                if source_candidate is not None and (
                    revised_plan.solutions == source_candidate.solutions
                    and revised_plan.validation_plan == source_candidate.validation_plan
                ):
                    raise ValueError(
                        "Panel revised_plan must change solutions or validation_plan"
                    )
                revised_plan.source = "panel"
                merged[revised_plan.candidate_id] = revised_plan
        return list(merged.values())

    @staticmethod
    def _validate_case_evidence(
        candidates: list[CandidatePlan],
        evidence: list[object],
        case_hits: list[dict],
    ) -> None:
        """Fail closed when the evidence agent invents or omits evidence."""
        candidate_ids = {candidate.candidate_id for candidate in candidates}
        hit_ids = {str(hit.get("case_id")) for hit in case_hits}
        evidence_ids = {getattr(item, "candidate_id", "") for item in evidence}
        missing = candidate_ids - evidence_ids
        unknown = evidence_ids - candidate_ids
        if missing or unknown:
            raise ValueError(
                f"Case evidence coverage invalid; missing={sorted(missing)}, "
                f"unknown={sorted(unknown)}"
            )
        for item in evidence:
            supporting = getattr(item, "supporting_cases", [])
            for case in supporting:
                if case.case_id not in hit_ids:
                    raise ValueError(
                        f"Evidence for {item.candidate_id} references unknown case "
                        f"{case.case_id}"
                    )
            if getattr(item, "match_status", "none") == "strong" and not supporting:
                raise ValueError(
                    f"Evidence for {item.candidate_id} is strong but has no supporting cases"
                )

    async def _check_cancelled(self) -> None:
        """检查是否收到取消信号，若已取消则发布通知并抛出 CancelledError。"""
        persistent_cancel = False
        if self.work_dir:
            persistent_cancel = is_task_cancel_requested(Path(self.work_dir).parent if self.run_id != "initial" else self.work_dir)
        if (self.cancel_event and self.cancel_event.is_set()) or persistent_cancel:
            await redis_manager.publish_message(
                self.task_id,
                SystemMessage(content="任务已停止", type="warning"),
            )
            raise asyncio.CancelledError("任务被用户停止")

    async def execute(
        self, problem: Problem, run_id: str | None = None
    ):  # type: ignore[reportIncompatibleMethodOverride]
        """Run the workflow with one uniform lifecycle/error boundary."""
        self.task_id = problem.task_id
        self.work_dir = self._prepare_work_dir(self.task_id, run_id)
        self._write_json("problem.json", problem.model_dump())
        self._write_state(
            "workflow",
            "running",
            run_id=self.run_id,
            artifacts=["problem.json"],
        )
        try:
            return await self._execute(problem)
        except asyncio.CancelledError:
            self._write_state("workflow", "cancelled")
            raise
        except Exception as exc:
            logger.exception("MathModelWorkFlow failed for %s", self.task_id)
            self._write_state("workflow", "failed", error=str(exc))
            raise

    async def _execute(self, problem: Problem):  # type: ignore[reportIncompatibleMethodOverride]
        """执行数学建模工作流。

        Args:
            problem: 包含题目信息、模板配置等的 Problem 对象。
        """
        # 在创建 LLM 前预校验配置，避免进入 Agent 循环后才发现缺配置
        missing = []
        for name, model_val, key_val in [
            ("Coordinator", settings.COORDINATOR_MODEL, settings.COORDINATOR_API_KEY),
            ("Modeler", settings.MODELER_MODEL, settings.MODELER_API_KEY),
            ("Coder", settings.CODER_MODEL, settings.CODER_API_KEY),
            ("Writer", settings.WRITER_MODEL, settings.WRITER_API_KEY),
        ]:
            if not model_val or not str(model_val).strip():
                missing.append(f"{name} 模型 ID")
            if not key_val or not str(key_val).strip():
                missing.append(f"{name} API Key")
        if missing:
            raise ValueError(f"以下配置缺失，请先在设置中填写并保存：{', '.join(missing)}")

        llm_factory = LLMFactory(self.task_id)
        coordinator_llm, modeler_llm, coder_llm, writer_llm = llm_factory.get_all_llms()

        coordinator_agent = CoordinatorAgent(
            self.task_id, coordinator_llm,
            context_window=settings.COORDINATOR_CONTEXT_WINDOW,
            cancel_event=self.cancel_event,
        )

        await redis_manager.publish_message(
            self.task_id,
            SystemMessage(content="识别用户意图和拆解问题ing..."),
        )

        await self._check_cancelled()

        try:
            checkpoint = self._read_json("coordinator.json")
            if isinstance(checkpoint, dict):
                coordinator_response = CoordinatorToModeler.model_validate(checkpoint)
                self._write_state("coordinator", "resumed", artifacts=["coordinator.json"])
            else:
                coordinator_response = await coordinator_agent.run(problem.ques_all)
                self._write_json("coordinator.json", coordinator_response.model_dump())
                self._write_state(
                    "coordinator",
                    "completed",
                    artifacts=["coordinator.json", "workflow_state.json"],
                )
            self.questions = coordinator_response.questions
            self.ques_count = coordinator_response.ques_count
        except Exception as e:
            #  非数学建模问题
            logger.error(f"CoordinatorAgent 执行失败: {e}")
            self._write_state("coordinator", "failed")
            raise e

        await redis_manager.publish_message(
            self.task_id,
            SystemMessage(content="识别用户意图和拆解问题完成,任务转交给建模手"),
        )

        await redis_manager.publish_message(
            self.task_id,
            SystemMessage(content="建模手开始建模ing..."),
        )

        await self._check_cancelled()

        modeler_agent = ModelerAgent(
            self.task_id, modeler_llm,
            context_window=settings.MODELER_CONTEXT_WINDOW,
            cancel_event=self.cancel_event,
        )

        self._write_state("modeler", "running")
        modeler_checkpoint = self._read_json("modeler_initial.json")
        if isinstance(modeler_checkpoint, dict):
            modeler_response = ModelerToCoder.model_validate(modeler_checkpoint)
            self._write_state("modeler", "resumed", artifacts=["modeler_initial.json"])
        else:
            modeler_response = await modeler_agent.run(coordinator_response)
            self._write_json("modeler_initial.json", modeler_response.model_dump())
            self._write_state(
                "modeler",
                "completed",
                artifacts=[
                    "coordinator.json",
                    "modeler_initial.json",
                    "workflow_state.json",
                ],
            )

        user_output = UserOutput(work_dir=self.work_dir, ques_count=self.ques_count)

        await redis_manager.publish_message(
            self.task_id,
            SystemMessage(content="正在创建代码沙盒环境"),
        )

        self._write_state("interpreter", "running")
        try:
            notebook_serializer = NotebookSerializer(work_dir=self.work_dir)
            code_interpreter = await create_interpreter(
                kind="local",
                task_id=self.task_id,
                work_dir=self.work_dir,
                notebook_serializer=notebook_serializer,
                timeout=3000,
            )
        except Exception as exc:
            self._write_state("interpreter", "failed", error=str(exc))
            raise
        self._write_state("interpreter", "completed")
        
        scholar = OpenAlexScholar(
            task_id=self.task_id,
            email=settings.OPENALEX_EMAIL,
            api_key=settings.OPENALEX_API_KEY,
        )

        await redis_manager.publish_message(
            self.task_id,
            SystemMessage(content="创建完成"),
        )

        await redis_manager.publish_message(
            self.task_id,
            SystemMessage(content="初始化代码手"),
        )

        # modeler_agent
        coder_agent = CoderAgent(
            task_id=problem.task_id,
            model=coder_llm,
            work_dir=self.work_dir,
            max_chat_turns=settings.MAX_CHAT_TURNS,
            max_retries=settings.MAX_RETRIES,
            code_interpreter=code_interpreter,
            context_window=settings.CODER_CONTEXT_WINDOW,
            cancel_event=self.cancel_event,
        )

        writer_agent = WriterAgent(
            task_id=problem.task_id,
            model=writer_llm,
            comp_template=problem.comp_template,
            format_output=problem.format_output,
            scholar=scholar,
            context_window=settings.WRITER_CONTEXT_WINDOW,
            cancel_event=self.cancel_event,
        )

        candidates = self._normalize_candidates(modeler_response)
        case_library = LocalCaseLibrary(settings.CASE_LIBRARY_PATH)
        search_query = "\n".join(
            [
                problem.ques_all,
                json.dumps(self.questions, ensure_ascii=False),
                *[candidate.description for candidate in candidates],
            ]
        )
        self._write_state("case_evidence", "running")
        saved_hits = self._read_json("case_hits.json")
        if isinstance(saved_hits, list):
            case_hits = [hit for hit in saved_hits if isinstance(hit, dict)]
        else:
            try:
                case_hits = [
                    hit.model_dump()
                    for hit in case_library.search(search_query, settings.CASE_SEARCH_LIMIT)
                ]
            except Exception as exc:
                logger.warning("Local case library search failed: %s", exc)
                case_hits = []
            if (
                not case_hits
                and settings.CASE_SEARCH_EXTERNAL
                and settings.OPENALEX_EMAIL
            ):
                try:
                    papers = await scholar.search_papers(
                        search_query[:3000], limit=settings.CASE_SEARCH_LIMIT
                    )
                    case_hits = [
                        {
                            "case_id": f"openalex:{index}",
                            "title": paper.get("title", ""),
                            "path": paper.get("doi") or "",
                            "score": 0.25,
                            "excerpt": paper.get("abstract", ""),
                        }
                        for index, paper in enumerate(papers)
                    ]
                except Exception as exc:
                    logger.warning("External case evidence search failed: %s", exc)
            self._write_json("case_hits.json", case_hits)

        case_agent = CaseEvidenceAgent(
            self.task_id,
            modeler_llm,
            context_window=settings.MODELER_CONTEXT_WINDOW,
            cancel_event=self.cancel_event,
        )
        saved_evidence = self._read_json("case_evidence.json")
        if isinstance(saved_evidence, list):
            evidence = [CaseEvidence.model_validate(item) for item in saved_evidence]
            self._write_state("case_evidence", "resumed", hit_count=len(case_hits))
        else:
            try:
                evidence = await case_agent.run(
                    problem.ques_all,
                    coordinator_response,
                    candidates,
                    case_hits,
                )
            except Exception:
                self._write_state("case_evidence", "failed")
                raise
        self._validate_case_evidence(candidates, evidence, case_hits)
        self._write_json("case_evidence.json", [item.model_dump() for item in evidence])
        self._write_state(
            "case_evidence",
            "completed",
            hit_count=len(case_hits),
            artifacts=["case_evidence.json", "workflow_state.json"],
        )

        panel_opinions = []
        saved_panel = self._read_json("case_panel.json")
        if isinstance(saved_panel, list):
            panel_opinions = [PanelOpinion.model_validate(item) for item in saved_panel]
            self._write_state("case_panel", "resumed", opinion_count=len(panel_opinions))
        elif not case_hits or any(item.match_status != "strong" for item in evidence):
            self._write_state("case_panel", "running")
            panel_agent = CasePanelAgent(
                self.task_id,
                modeler_llm,
                context_window=settings.MODELER_CONTEXT_WINDOW,
                cancel_event=self.cancel_event,
            )
            try:
                panel_opinions = await panel_agent.run(
                    problem.ques_all,
                    candidates,
                    evidence,
                )
            except Exception:
                self._write_state("case_panel", "failed")
                raise
            self._write_state(
                "case_panel",
                "completed",
                opinion_count=len(panel_opinions),
                artifacts=["case_panel.json", "workflow_state.json"],
            )
        else:
            self._write_state(
                "case_panel",
                "skipped",
                reason="all candidates have strong case evidence",
                artifacts=["workflow_state.json"],
            )
        candidates = self._apply_panel_revisions(candidates, panel_opinions)
        self._write_json(
            "case_panel.json", [item.model_dump() for item in panel_opinions]
        )

        chief_agent = ChiefPlannerAgent(
            self.task_id,
            modeler_llm,
            context_window=settings.MODELER_CONTEXT_WINDOW,
            cancel_event=self.cancel_event,
        )
        self._write_state("plan_selection", "running")
        saved_decision = self._read_json("chief_decision.json")
        if isinstance(saved_decision, dict):
            decision = DecisionRecord.model_validate(saved_decision)
            self._write_state(
                "plan_selection",
                "resumed",
                selected_candidate_id=decision.selected_candidate_id,
            )
        else:
            try:
                decision = await chief_agent.run(
                    problem.ques_all,
                    candidates,
                    evidence,
                    panel_opinions,
                )
            except Exception:
                self._write_state("plan_selection", "failed")
                raise
        self._write_json("chief_decision.json", decision.model_dump())
        selected_solutions = decision.selected_plan.solutions or {
            key: value
            for key, value in modeler_response.questions_solution.items()
            if isinstance(value, str)
        }
        selected_modeler_response = ModelerToCoder(
            questions_solution=selected_solutions
        )
        self._write_state(
            "plan_selection",
            "completed",
            selected_candidate_id=decision.selected_candidate_id,
            artifacts=[
                "coordinator.json",
                "modeler_initial.json",
                "case_evidence.json",
                "case_panel.json",
                "chief_decision.json",
                "workflow_state.json",
            ],
        )

        flows = Flows(self.questions)

        ################################################ solution steps
        solution_flows = flows.get_solution_flows(
            self.questions, selected_modeler_response
        )
        config_template = get_config_template(problem.comp_template)
        validation_feedback: list[dict] = []
        decision_round = 1

        for key, value in solution_flows.items():
            await self._check_cancelled()
            prompt_digest = self._checkpoint_digest(
                decision.selected_candidate_id, key, value.get("coder_prompt", "")
            )
            self._write_state(
                "coder",
                "running",
                subtask=key,
                selected_candidate_id=decision.selected_candidate_id,
            )

            await redis_manager.publish_message(
                self.task_id,
                SystemMessage(content=f"代码手开始求解{key}"),
            )

            coder_response, checkpoint_summary = self._load_coder_checkpoint(
                key, decision.selected_candidate_id, prompt_digest
            )
            resumed_coder = coder_response is not None
            if coder_response is None:
                coder_response = await coder_agent.run(
                    prompt=value["coder_prompt"], subtask_title=key
                )
            else:
                self._restore_coder_output(code_interpreter, key, coder_response)
                self._write_state(
                    "coder", "resumed", subtask=key,
                    selected_candidate_id=decision.selected_candidate_id,
                )
            self._write_json(
                f"coder_validation_{decision_round}_{key}.json",
                {
                    "subtask": key,
                    "success": coder_response.success,
                    "error_message": coder_response.error_message,
                    "attempts": coder_response.attempts,
                    "executed_code": coder_response.executed_code,
                    "validation_passed": coder_response.validation_passed,
                    "validation_summary": coder_response.validation_summary,
                    "output_files": coder_response.output_files,
                    "metrics": coder_response.metrics,
                    "code_response": coder_response.code_response,
                },
            )
            coder_valid, validation_summary = validate_coder_response(coder_response)
            if coder_valid:
                if not coder_response.code_output:
                    try:
                        coder_response.code_output = code_interpreter.get_code_output(key)
                    except (AttributeError, KeyError):
                        pass
                self._save_coder_checkpoint(
                    key, decision.selected_candidate_id, prompt_digest, coder_response
                )
            self._write_state(
                "coder",
                "completed" if coder_valid else "failed",
                subtask=key,
                selected_candidate_id=decision.selected_candidate_id,
            )

            if not coder_valid:
                feedback = {
                    "subtask": key,
                    "error_message": coder_response.error_message
                    or coder_response.code_response
                    or "unknown validation failure",
                    "attempts": coder_response.attempts,
                    "validation_summary": validation_summary,
                }
                validation_feedback.append(feedback)
                self._write_state(
                    "plan_selection",
                    "running",
                    reason="coder validation failed",
                    failed_subtask=key,
                )
                recovery_panel = CasePanelAgent(
                    self.task_id,
                    modeler_llm,
                    context_window=settings.MODELER_CONTEXT_WINDOW,
                    cancel_event=self.cancel_event,
                )
                recovery_opinions = await recovery_panel.run(
                    problem.ques_all
                    + "\nImplementation validation feedback:\n"
                    + json.dumps(validation_feedback, ensure_ascii=False),
                    candidates,
                    evidence,
                )
                candidates = self._apply_panel_revisions(candidates, recovery_opinions)
                decision_round += 1
                decision = await chief_agent.run(
                    problem.ques_all,
                    candidates,
                    evidence,
                    recovery_opinions,
                    validation_feedback=validation_feedback,
                )
                self._write_json(
                    f"chief_decision_round_{decision_round}.json",
                    decision.model_dump(),
                )
                self._write_json("chief_decision.json", decision.model_dump())
                selected_modeler_response = ModelerToCoder(
                    questions_solution=decision.selected_plan.solutions
                )
                solution_flows.update(
                    flows.get_solution_flows(
                        self.questions, selected_modeler_response
                    )
                )
                self._write_state(
                    "plan_selection",
                    "completed",
                    selected_candidate_id=decision.selected_candidate_id,
                    decision_round=decision_round,
                    validation_feedback=validation_feedback,
                )
                retry_value = solution_flows[key]
                retry_response = await coder_agent.run(
                    prompt=retry_value["coder_prompt"], subtask_title=key
                )
                self._write_json(
                    f"coder_validation_{decision_round}_{key}_retry.json",
                    {
                        "subtask": key,
                        "success": retry_response.success,
                        "error_message": retry_response.error_message,
                        "attempts": retry_response.attempts,
                        "executed_code": retry_response.executed_code,
                        "validation_passed": retry_response.validation_passed,
                        "validation_summary": retry_response.validation_summary,
                        "output_files": retry_response.output_files,
                        "metrics": retry_response.metrics,
                        "code_response": retry_response.code_response,
                    },
                )
                retry_valid, retry_summary = validate_coder_response(retry_response)
                if not retry_valid:
                    self._write_state(
                        "coder",
                        "failed",
                        subtask=key,
                        selected_candidate_id=decision.selected_candidate_id,
                        reason="validation failed after plan re-evaluation",
                    )
                    raise RuntimeError(
                        f"Coder validation failed for {key} after plan re-evaluation"
                    )
                coder_response = retry_response
                retry_prompt_digest = self._checkpoint_digest(
                    decision.selected_candidate_id,
                    key,
                    retry_value.get("coder_prompt", ""),
                )
                self._save_coder_checkpoint(
                    key,
                    decision.selected_candidate_id,
                    retry_prompt_digest,
                    coder_response,
                )
                self._write_state(
                    "coder",
                    "completed",
                    subtask=key,
                    selected_candidate_id=decision.selected_candidate_id,
                    recovered_after_plan_review=True,
                )

            await redis_manager.publish_message(
                self.task_id,
                SystemMessage(content=f"代码手求解成功{key}", type="success"),
            )

            self._write_state("writer", "running", subtask=key)
            writer_prompt = flows.get_writer_prompt(
                key, coder_response.code_response or "", code_interpreter, config_template
            )
            writer_digest = self._checkpoint_digest(
                decision.selected_candidate_id, key, writer_prompt,
                coder_response.code_response or "", coder_response.code_output or "",
            )

            await redis_manager.publish_message(
                self.task_id,
                SystemMessage(content=f"论文手开始写{key}部分"),
            )

            ## TODO: 图片引用错误
            writer_response = self._load_writer_checkpoint(
                "writer_checkpoint", key, writer_digest
            )
            if writer_response is None:
                try:
                    writer_response = await writer_agent.run(
                    writer_prompt,
                    available_images=coder_response.created_images,
                    sub_title=key,
                    )
                except Exception as exc:
                    self._write_state("writer", "failed", subtask=key, error=str(exc))
                    raise
                if not str(writer_response.response_content or "").strip():
                    raise RuntimeError(f"Writer returned an empty section for {key}")
                self._save_writer_checkpoint(
                    "writer_checkpoint", key, writer_digest, writer_response
                )
            else:
                self._write_state("writer", "resumed", subtask=key)
            self._write_state("writer", "completed", subtask=key)

            await redis_manager.publish_message(
                self.task_id,
                SystemMessage(content=f"论文手完成{key}部分"),
            )

            user_output.set_res(key, writer_response)

        # 关闭沙盒

        await code_interpreter.cleanup()
        logger.info(user_output.get_res())

        ################################################ write steps

        write_flows = flows.get_write_flows(
            user_output, config_template, problem.ques_all
        )
        for key, value in write_flows.items():
            await self._check_cancelled()
            self._write_state("writer", "running", subtask=key)
            write_digest = self._checkpoint_digest(key, value)

            await redis_manager.publish_message(
                self.task_id,
                SystemMessage(content=f"论文手开始写{key}部分"),
            )

            writer_response = self._load_writer_checkpoint(
                "final_writer_checkpoint", key, write_digest
            )
            if writer_response is None:
                try:
                    writer_response = await writer_agent.run(prompt=value, sub_title=key)
                except Exception as exc:
                    self._write_state("writer", "failed", subtask=key, error=str(exc))
                    raise
                if not str(writer_response.response_content or "").strip():
                    raise RuntimeError(f"Writer returned an empty section for {key}")
                self._save_writer_checkpoint(
                    "final_writer_checkpoint", key, write_digest, writer_response
                )
            else:
                self._write_state("writer", "resumed", subtask=key)
            self._write_state("writer", "completed", subtask=key)

            user_output.set_res(key, writer_response)

        logger.info(user_output.get_res())

        user_output.save_result()
        self._write_state(
            "completed",
            "completed",
            selected_candidate_id=decision.selected_candidate_id,
            artifacts=[
                "coordinator.json",
                "modeler_initial.json",
                "case_evidence.json",
                "case_panel.json",
                "chief_decision.json",
                "res.json",
                "res.md",
                "workflow_state.json",
            ],
        )
