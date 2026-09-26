import pytest

from dicojev.controller import ThresholdRiskController
from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.schemas import (
    CoverageScore,
    DecisionBackendResult,
    FeedbackBundle,
    FeedbackCode,
    FeedbackSignal,
    MetaAction,
    SelectionScore,
)


def result(coverage, confidence=0.9, selected="A"):
    probabilities = {selected: confidence, "N": 1 - confidence} if selected != "N" else {"N": 1.0}
    return DecisionBackendResult(
        backend="mock",
        coverage=CoverageScore(raw=coverage, method="scripted"),
        selection=SelectionScore(
            selected_id=selected,
            probabilities=probabilities,
            confidence_raw=confidence,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("backend_result", "remaining", "expected"),
    [
        (result(0.9), 1, MetaAction.ACT),
        (result(0.2), 1, MetaAction.EXPAND),
        (result(0.2), 0, MetaAction.ABSTAIN),
        (DecisionBackendResult(backend="mock"), 1, MetaAction.ESCALATE),
    ],
)
async def test_all_controller_actions(backend_result, remaining, expected):
    decision = await ThresholdRiskController().decide(
        backend_result, round_index=0, expansions_remaining=remaining
    )
    assert decision.action is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("code", list(FeedbackCode))
async def test_feedback_compilation_is_deterministic(code):
    compiler = DeterministicFeedbackCompiler()
    details = {"requested_new_candidates": 2} if code in {
        FeedbackCode.MISSING_ACTION,
        FeedbackCode.AMBIGUOUS_SELECTION,
        FeedbackCode.REDUNDANT_SET,
    } else {}
    bundle = FeedbackBundle(
        primary=FeedbackSignal(code=code, details=details),
        source_round=0,
        controller_reason_code="fixture",
        generation_relevant=code is not FeedbackCode.ADEQUATE,
    )
    assert await compiler.compile(bundle) == await compiler.compile(bundle)


@pytest.mark.asyncio
async def test_q_cov_is_not_derived_from_q_sel():
    decision = await ThresholdRiskController().decide(
        DecisionBackendResult(
            backend="mock",
            selection=SelectionScore(
                selected_id="A", probabilities={"A": 1.0}, confidence_raw=1.0
            ),
        ),
        round_index=0,
        expansions_remaining=1,
    )
    assert decision.action is MetaAction.ESCALATE
