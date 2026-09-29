import pytest

from dicojev.schemas import (
    Candidate,
    CoverageScore,
    DecisionBackendResult,
    FeedbackCode,
    MetaAction,
    SelectionScore,
)
from dicojev.v4 import (
    CostAwareRiskController,
    FastSlowRouter,
    FeedbackRecoveryPolicy,
    RecoveryObservation,
    candidate_set_features,
    conformal_coverage_threshold,
    controlled_corruptions,
    risk_latency_token_curve,
)


def backend_result(
    coverage: float,
    selection: float = 0.9,
    *,
    coverage_calibrated: float | None = None,
    selection_calibrated: float | None = None,
) -> DecisionBackendResult:
    return DecisionBackendResult(
        backend="fixture",
        coverage=CoverageScore(
            raw=coverage,
            calibrated=coverage_calibrated,
            method="fixture",
        ),
        selection=SelectionScore(
            selected_id="A",
            probabilities={"A": selection, "N": 1 - selection},
            confidence_raw=selection,
            confidence_calibrated=selection_calibrated,
        ),
    )


def recovery_policy() -> FeedbackRecoveryPolicy:
    return FeedbackRecoveryPolicy.fit(
        [
            RecoveryObservation(FeedbackCode.MISSING_ACTION, True, 10),
            RecoveryObservation(FeedbackCode.MISSING_ACTION, True, 14),
            RecoveryObservation(FeedbackCode.AMBIGUOUS_SELECTION, False, 30),
            RecoveryObservation(FeedbackCode.AMBIGUOUS_SELECTION, False, 20),
        ]
    )


def test_candidate_features_and_controlled_corruptions_are_deterministic():
    candidates = [
        Candidate(id="A", action="Verify recipient", tool="address_book"),
        Candidate(id="B", action="Send now", constraint_violations=("must verify",)),
    ]
    features = candidate_set_features(candidates)
    assert features == {
        "candidate_count": 2.0,
        "unique_ratio": 1.0,
        "tool_coverage": 0.5,
        "constraint_compliance": 0.5,
    }
    corruptions = controlled_corruptions(candidates, acceptable_ids={"A"})
    assert [case.name for case in corruptions] == [
        "adequate",
        "acceptable_deleted",
        "duplicate_added",
        "distractor_added",
    ]
    assert [candidate.id for candidate in corruptions[1].candidates] == ["B"]
    assert corruptions[1].adequate is False
    assert len(corruptions[2].candidates) == 3
    with pytest.raises(ValueError):
        controlled_corruptions([], acceptable_ids=set())


def test_feedback_recovery_policy_learns_probability_and_token_cost():
    policy = recovery_policy()
    assert policy.recovery_probability(FeedbackCode.MISSING_ACTION) == pytest.approx(0.75)
    assert policy.recovery_probability(FeedbackCode.AMBIGUOUS_SELECTION) == pytest.approx(0.25)
    assert policy.expected_token_cost(FeedbackCode.MISSING_ACTION) == 12
    assert policy.recovery_probability(FeedbackCode.TOOL_MISMATCH) == 0.5


@pytest.mark.asyncio
async def test_cost_aware_controller_expands_only_when_expected_recovery_justifies_cost():
    policy = recovery_policy()
    permissive = CostAwareRiskController(policy, expansion_cost=0.5)
    expensive = CostAwareRiskController(policy, expansion_cost=0.8)
    budgets = {
        "round_index": 0,
        "expansions_remaining": 1,
        "candidate_budget_remaining": 2,
    }
    assert (await permissive.decide(backend_result(0.2), **budgets)).action is MetaAction.EXPAND
    rejected = await expensive.decide(backend_result(0.2), **budgets)
    assert rejected.action is MetaAction.ABSTAIN
    assert rejected.reason_code == "adaptive_cost_exceeds_expected_recovery"
    assert rejected.feedback.generation_relevant is False


def test_fast_slow_router_honors_zero_calibrated_values():
    router = FastSlowRouter()
    assert router.route(backend_result(0.95, 0.95)) == "fast_accept"
    assert router.route(backend_result(0.95, 0.95, coverage_calibrated=0.0)) == "slow_verify"
    assert router.route(DecisionBackendResult(backend="empty")) == "fail_closed"


def test_conformal_threshold_and_risk_cost_curve():
    assert conformal_coverage_threshold([0.2, 0.5, 0.8, 0.9], miscoverage=0.25) == 0.5
    with pytest.raises(ValueError):
        conformal_coverage_threshold([], miscoverage=0.1)
    curve = risk_latency_token_curve(
        [
            {"coverage_threshold": 0.7, "error": False, "latency_ms": 10, "tokens": 5},
            {"coverage_threshold": 0.7, "error": True, "latency_ms": 20, "tokens": 7},
            {"coverage_threshold": 0.9, "error": False, "latency_ms": 30, "tokens": 9},
        ]
    )
    assert curve == [
        {"coverage_threshold": 0.7, "risk": 0.5, "mean_latency_ms": 15.0, "mean_tokens": 6.0},
        {"coverage_threshold": 0.9, "risk": 0.0, "mean_latency_ms": 30.0, "mean_tokens": 9.0},
    ]
