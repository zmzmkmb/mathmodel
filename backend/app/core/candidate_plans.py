"""Candidate-plan normalization shared by the workflow and focused tests."""

from app.schemas.A2A import ModelerToCoder
from app.schemas.decision import CandidatePlan


def normalize_candidates(modeler_response: ModelerToCoder) -> list[CandidatePlan]:
    """Support future multi-plan output while preserving the old contract."""
    raw = modeler_response.questions_solution
    declared = raw.get("_candidate_plans") if isinstance(raw, dict) else None
    if isinstance(declared, list):
        candidates = [
            CandidatePlan.model_validate(item)
            for item in declared
            if isinstance(item, dict)
        ]
        if candidates:
            return candidates

    solutions = {key: value for key, value in raw.items() if isinstance(value, str)}
    return [
        CandidatePlan(
            candidate_id="modeler_default",
            title="Modeler initial plan",
            description="The initial plan produced by Modeler.",
            solutions=solutions,
            source="modeler",
        )
    ]
