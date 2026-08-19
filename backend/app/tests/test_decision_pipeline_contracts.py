from app.core.candidate_plans import normalize_candidates
from app.schemas.A2A import ModelerToCoder
from app.schemas.decision import CandidatePlan
from app.schemas.decision import PanelOpinion


def test_legacy_modeler_output_becomes_one_candidate():
    response = ModelerToCoder(
        questions_solution={"ques1": "Use a regression model", "ques2": "Validate by CV"}
    )

    candidates = normalize_candidates(response)

    assert len(candidates) == 1
    assert candidates[0].candidate_id == "modeler_default"
    assert candidates[0].solutions["ques1"] == "Use a regression model"


def test_multi_plan_modeler_output_is_preserved():
    plan = CandidatePlan(
        candidate_id="p1",
        title="Baseline",
        description="A defensible baseline",
        solutions={"ques1": "Linear model"},
    )
    response = ModelerToCoder(
        questions_solution={"_candidate_plans": [plan.model_dump()]}
    )

    candidates = normalize_candidates(response)

    assert candidates == [plan]


def test_panel_opinion_can_carry_a_revised_plan():
    revised = CandidatePlan(
        candidate_id="p1-revised",
        title="Regularized baseline",
        description="A baseline with explicit regularization",
        source="panel",
    )

    opinion = PanelOpinion(
        candidate_id="p1",
        verdict="revise",
        revised_plan=revised,
    )

    assert opinion.revised_plan is not None
    assert opinion.revised_plan.source == "panel"
