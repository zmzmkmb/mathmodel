"""Agents that turn model ideas and case evidence into a locked plan."""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.agents.agent import Agent
from app.core.llm.llm import LLM
from app.schemas.decision import (
    CandidatePlan,
    CaseEvidence,
    DecisionRecord,
    PanelOpinion,
    PlanScore,
)
from app.schemas.A2A import CoordinatorToModeler, ModelerToCoder
from app.utils.log_util import logger


ModelT = TypeVar("ModelT", bound=BaseModel)


def _load_json(content: str) -> Any:
    cleaned = (content or "").replace("```json", "").replace("```", "").strip()
    if not cleaned.startswith(("{", "[")):
        starts = [index for index in (cleaned.find("{"), cleaned.find("[")) if index >= 0]
        if starts:
            cleaned = cleaned[min(starts):]
    if cleaned.startswith("{"):
        end = cleaned.rfind("}")
    else:
        end = cleaned.rfind("]")
    if end >= 0:
        cleaned = cleaned[: end + 1]
    return json.loads(cleaned)


def _parse_json(content: str, model_type: type[ModelT]) -> ModelT:
    try:
        return model_type.model_validate(_load_json(content))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"structured decision response is invalid: {exc}") from exc


class CaseEvidenceAgent(Agent):
    """Assess whether local case cards support the modeler's plans."""

    async def run(
        self,
        problem_text: str,
        coordinator: CoordinatorToModeler,
        candidates: list[CandidatePlan],
        case_hits: list[dict[str, Any]],
    ) -> list[CaseEvidence]:
        prompt = (
            "Assess historical evidence for the candidate plans below. "
            "Use only the supplied case cards; never invent a case. "
            "Return a JSON array. Each item must contain candidate_id, "
            "match_status (strong|partial|none), supporting_cases, "
            "transferable_patterns, applicability_limits, evidence_summary.\n\n"
            f"Problem:\n{problem_text}\n\n"
            f"Questions:\n{coordinator.questions}\n\n"
            f"Candidate plans:\n{json.dumps([item.model_dump() for item in candidates], ensure_ascii=False)}\n\n"
            f"Case cards:\n{json.dumps(case_hits, ensure_ascii=False)}"
        )
        await self.append_chat_history({"role": "system", "content": prompt})
        response = await self._chat(
            history=self.chat_history,
            agent_name="CaseEvidenceAgent",
        )
        raw = response.content or "[]"
        data = _load_json(raw)
        return [CaseEvidence.model_validate(item) for item in data]


class CasePanelAgent(Agent):
    """Debate unsupported plans and turn uncertainty into test requirements."""

    async def run(
        self,
        problem_text: str,
        candidates: list[CandidatePlan],
        evidence: list[CaseEvidence],
    ) -> list[PanelOpinion]:
        prompt = (
            "Act as a skeptical mathematical-modeling review panel. "
            "Review candidates with weak or absent case evidence. "
            "Return a JSON array of PanelOpinion objects. "
            "Each opinion may include revised_plan when the original plan needs "
            "a concrete change; revised_plan.source must be panel. "
            "Do not reject a plan only because no historical case exists; "
            "instead require stronger derivation, baseline comparison, or "
            "sensitivity tests when appropriate.\n\n"
            f"Problem:\n{problem_text}\n"
            f"Candidates:\n{json.dumps([item.model_dump() for item in candidates], ensure_ascii=False)}\n"
            f"Evidence:\n{json.dumps([item.model_dump() for item in evidence], ensure_ascii=False)}"
        )
        await self.append_chat_history({"role": "system", "content": prompt})
        response = await self._chat(
            history=self.chat_history,
            agent_name="CasePanelAgent",
        )
        raw = response.content or "[]"
        data = _load_json(raw)
        return [PanelOpinion.model_validate(item) for item in data]


class ChiefPlannerAgent(Agent):
    """Score all candidates and lock exactly one plan for downstream coding."""

    async def run(
        self,
        problem_text: str,
        candidates: list[CandidatePlan],
        evidence: list[CaseEvidence],
        panel: list[PanelOpinion],
        validation_feedback: list[dict[str, Any]] | None = None,
    ) -> DecisionRecord:
        prompt = (
            "You are the chief planner for a mathematical-modeling workflow. "
            "Select exactly one candidate plan for implementation. "
            "Score correctness, evidence_strength, feasibility, validation_cost, "
            "and innovation from 0 to 10. Higher validation_cost means harder, "
            "so subtract it in total. Prefer a defensible, finishable plan over "
            "an impressive but unsupported one. Return one DecisionRecord JSON.\n\n"
            f"Problem:\n{problem_text}\n"
            f"Candidates:\n{json.dumps([item.model_dump() for item in candidates], ensure_ascii=False)}\n"
            f"Evidence:\n{json.dumps([item.model_dump() for item in evidence], ensure_ascii=False)}\n"
            f"Panel opinions:\n{json.dumps([item.model_dump() for item in panel], ensure_ascii=False)}\n"
            f"Implementation validation feedback:\n{json.dumps(validation_feedback or [], ensure_ascii=False)}"
        )
        await self.append_chat_history({"role": "system", "content": prompt})
        response = await self._chat(
            history=self.chat_history,
            agent_name="ChiefPlannerAgent",
        )
        raw = response.content or "{}"
        decision = _parse_json(raw, DecisionRecord)
        candidate_ids = {item.candidate_id for item in candidates}
        if decision.selected_candidate_id not in candidate_ids:
            raise ValueError(
                "ChiefPlanner selected an unknown candidate: "
                f"{decision.selected_candidate_id}"
            )
        logger.info(
            "ChiefPlanner locked candidate %s",
            decision.selected_candidate_id,
        )
        return decision
