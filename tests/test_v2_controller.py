import asyncio

import pytest

from dicojev.backends import MockDecisionBackend
from dicojev.controller import ThresholdRiskController
from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import FakeCandidateGenerator
from dicojev.harness import DecisionOrchestrator, evaluate_candidate_quality
from dicojev.schemas import (
    Candidate,
    CoverageScore,
    DecisionBackendResult,
    DecisionBudget,
    FeedbackCode,
    MetaAction,
    SelectionScore,
)


def evidence(coverage=0.9, selected="A", confidence=0.9):
    probabilities = {"N": 1.0} if selected == "N" else {selected: confidence, "N": 1 - confidence}
    return DecisionBackendResult(
        backend="mock",
        coverage=CoverageScore(raw=coverage, method="fixture"),
        selection=SelectionScore(
            selected_id=selected,
            probabilities=probabilities,
            confidence_raw=confidence,
        ),
    )


def test_rule_quality_flags_tool_constraint_format_and_redundancy(decision_request):
    request = decision_request.model_copy(
        update={"available_tools": ("review",), "constraints": ("Do not send",)}
    )
    candidates = [
        Candidate(id="A", action="Review draft carefully", tool="review"),
        Candidate(id="B", action="Review the draft carefully", tool="missing"),
        Candidate(
            id="C",
            action="Send now",
            constraint_violations=("Do not send",),
        ),
        Candidate(id="D", action="x" * 501),
    ]
    quality = evaluate_candidate_quality(candidates, request)
    assert quality["B"].tool_available is False
    assert quality["C"].constraint_compliant is False
    assert quality["D"].syntactically_valid is False
    assert quality["A"].redundancy_group == quality["B"].redundancy_group


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("quality", "expected"),
    [
        ({"tool_available": False}, FeedbackCode.TOOL_MISMATCH),
        ({"constraint_compliant": False}, FeedbackCode.CONSTRAINT_FAILURE),
        ({"redundancy_group": "r1"}, FeedbackCode.REDUNDANT_SET),
    ],
)
async def test_quality_feedback_changes_controller_behavior(quality, expected):
    from dicojev.schemas import CandidateQuality

    result = evidence().model_copy(
        update={"candidate_quality": {"A": CandidateQuality(candidate_id="A", **quality)}}
    )
    decision = await ThresholdRiskController().decide(
        result,
        round_index=0,
        expansions_remaining=1,
        candidate_budget_remaining=2,
    )
    assert decision.action is MetaAction.EXPAND
    assert decision.feedback.primary.code is expected


@pytest.mark.asyncio
async def test_compute_budget_prevents_another_diffusion_pair(decision_request):
    request = decision_request.model_copy(
        update={"budget": DecisionBudget(max_candidates=4, max_expansions=2, compute_units=2)}
    )
    response = await DecisionOrchestrator(
        FakeCandidateGenerator([["Send now"], ["Review"]]),
        MockDecisionBackend([evidence(coverage=0.1, selected="N", confidence=0.9)]),
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
    ).run(request)
    assert response.action is MetaAction.ABSTAIN
    assert response.total_compute_units == 2
    assert len(response.trace) == 1
    assert response.trace[0].remaining_compute_units == 0


@pytest.mark.asyncio
async def test_latency_budget_prevents_expansion_after_completed_read(decision_request):
    class SlowGenerator(FakeCandidateGenerator):
        async def generate(self, request, context=None):
            await asyncio.sleep(0.02)
            return await super().generate(request, context)

    request = decision_request.model_copy(
        update={"budget": DecisionBudget(max_candidates=4, max_expansions=1, latency_ms=5)}
    )
    response = await DecisionOrchestrator(
        SlowGenerator([["Send now"], ["Review"]]),
        MockDecisionBackend([evidence(coverage=0.1, selected="N", confidence=0.9)]),
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
    ).run(request)
    assert response.action is MetaAction.ABSTAIN
    assert len(response.trace) == 1
    assert response.trace[0].remaining_latency_ms == 0
    assert "latency_budget_exhausted" in response.controller.reason_code

