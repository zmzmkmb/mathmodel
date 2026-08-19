"""Structured contracts for model selection and case evidence."""

from typing import Literal

from pydantic import BaseModel, Field


class CandidatePlan(BaseModel):
    """A model plan proposed by the modeler."""

    candidate_id: str
    title: str
    description: str
    assumptions: list[str] = Field(default_factory=list)
    validation_plan: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    solutions: dict[str, str] = Field(default_factory=dict)
    source: Literal["modeler", "panel", "chief"] = "modeler"


class CaseHit(BaseModel):
    """A local case-card hit supplied to the case agent."""

    case_id: str
    title: str
    path: str
    score: float
    excerpt: str


class CaseEvidence(BaseModel):
    """Evidence assessment for one candidate plan."""

    candidate_id: str
    match_status: Literal["strong", "partial", "none"]
    supporting_cases: list[CaseHit] = Field(default_factory=list)
    transferable_patterns: list[str] = Field(default_factory=list)
    applicability_limits: list[str] = Field(default_factory=list)
    evidence_summary: str = ""


class PanelOpinion(BaseModel):
    """Discussion output when historical evidence is weak or absent."""

    candidate_id: str
    verdict: Literal["support", "revise", "reject"]
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    required_revisions: list[str] = Field(default_factory=list)
    validation_requirements: list[str] = Field(default_factory=list)
    rationale: str = ""
    revised_plan: CandidatePlan | None = None


class PlanScore(BaseModel):
    """Comparable scorecard used by the chief planner."""

    candidate_id: str
    correctness: float = 0.0
    evidence_strength: float = 0.0
    feasibility: float = 0.0
    validation_cost: float = 0.0
    innovation: float = 0.0
    total: float = 0.0
    rationale: str = ""


class DecisionRecord(BaseModel):
    """Final locked decision passed to the coding stage."""

    selected_candidate_id: str
    selected_plan: CandidatePlan
    scorecards: list[PlanScore] = Field(default_factory=list)
    evidence: list[CaseEvidence] = Field(default_factory=list)
    panel_opinions: list[PanelOpinion] = Field(default_factory=list)
    decision_rationale: str
    unresolved_risks: list[str] = Field(default_factory=list)
    mandatory_validations: list[str] = Field(default_factory=list)
