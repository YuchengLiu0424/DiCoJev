"""Adaptive-compute and ablation utilities for v4 research."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .controller import ThresholdRiskController
from .schemas import (
    Candidate,
    ControllerDecision,
    DecisionBackendResult,
    FeedbackCode,
    MetaAction,
)


@dataclass(frozen=True)
class CorruptionCase:
    name: str
    candidates: tuple[Candidate, ...]
    adequate: bool


def candidate_set_features(candidates: Sequence[Candidate]) -> dict[str, float]:
    count = len(candidates)
    if not count:
        return {
            "candidate_count": 0.0,
            "unique_ratio": 0.0,
            "tool_coverage": 0.0,
            "constraint_compliance": 0.0,
        }
    normalized = [" ".join(candidate.action.casefold().split()) for candidate in candidates]
    return {
        "candidate_count": float(count),
        "unique_ratio": len(set(normalized)) / count,
        "tool_coverage": sum(candidate.tool is not None for candidate in candidates) / count,
        "constraint_compliance": sum(
            not candidate.constraint_violations for candidate in candidates
        )
        / count,
    }


def controlled_corruptions(
    candidates: Sequence[Candidate], *, acceptable_ids: set[str]
) -> list[CorruptionCase]:
    if not candidates:
        raise ValueError("at least one candidate is required")
    retained = tuple(candidates)
    deleted = tuple(candidate for candidate in candidates if candidate.id not in acceptable_ids)
    duplicate = (
        *retained,
        retained[0].model_copy(update={"id": None, "original_action": retained[0].action}),
    )
    distractor = (
        *retained,
        Candidate(action="Take an unrelated action", original_action="controlled_distractor"),
    )
    return [
        CorruptionCase("adequate", retained, True),
        CorruptionCase("acceptable_deleted", deleted, False),
        CorruptionCase("duplicate_added", duplicate, True),
        CorruptionCase("distractor_added", distractor, True),
    ]


@dataclass(frozen=True)
class RecoveryObservation:
    code: FeedbackCode
    recovered: bool
    feedback_tokens: int


class FeedbackRecoveryPolicy:
    """Smoothed empirical recovery model over the typed feedback vocabulary."""

    def __init__(
        self,
        probabilities: dict[FeedbackCode, float],
        token_costs: dict[FeedbackCode, float],
    ) -> None:
        self.probabilities = probabilities
        self.token_costs = token_costs

    @classmethod
    def fit(
        cls, observations: Sequence[RecoveryObservation], *, prior_strength: float = 2.0
    ) -> FeedbackRecoveryPolicy:
        if not observations:
            raise ValueError("feedback recovery observations are required")
        grouped: dict[FeedbackCode, list[RecoveryObservation]] = defaultdict(list)
        for observation in observations:
            grouped[observation.code].append(observation)
        probabilities = {
            code: (sum(item.recovered for item in items) + prior_strength * 0.5)
            / (len(items) + prior_strength)
            for code, items in grouped.items()
        }
        token_costs = {
            code: sum(item.feedback_tokens for item in items) / len(items)
            for code, items in grouped.items()
        }
        return cls(probabilities, token_costs)

    def recovery_probability(self, code: FeedbackCode) -> float:
        return self.probabilities.get(code, 0.5)

    def expected_token_cost(self, code: FeedbackCode) -> float:
        return self.token_costs.get(code, 0.0)


class CostAwareRiskController:
    """Gate expansion when learned recovery value does not justify its configured cost."""

    def __init__(
        self,
        policy: FeedbackRecoveryPolicy,
        *,
        min_coverage: float = 0.75,
        min_selection: float = 0.70,
        expansion_cost: float = 0.2,
    ) -> None:
        self.base = ThresholdRiskController(min_coverage, min_selection)
        self.policy = policy
        self.expansion_cost = expansion_cost

    async def decide(
        self,
        result: DecisionBackendResult,
        *,
        round_index: int,
        expansions_remaining: int,
        candidate_budget_remaining: int | None = None,
        latency_budget_remaining: float | None = None,
        compute_budget_remaining: float | None = None,
    ) -> ControllerDecision:
        decision = await self.base.decide(
            result,
            round_index=round_index,
            expansions_remaining=expansions_remaining,
            candidate_budget_remaining=candidate_budget_remaining,
            latency_budget_remaining=latency_budget_remaining,
            compute_budget_remaining=compute_budget_remaining,
        )
        if decision.action is not MetaAction.EXPAND:
            return decision
        probability = self.policy.recovery_probability(decision.feedback.primary.code)
        if probability > self.expansion_cost:
            return decision
        feedback = decision.feedback.model_copy(update={"generation_relevant": False})
        return decision.model_copy(
            update={
                "action": MetaAction.ABSTAIN,
                "reason_code": "adaptive_cost_exceeds_expected_recovery",
                "feedback": feedback,
            }
        )


class FastSlowRouter:
    def __init__(self, *, fast_coverage: float = 0.9, fast_selection: float = 0.9) -> None:
        self.fast_coverage = fast_coverage
        self.fast_selection = fast_selection

    def route(
        self, result: DecisionBackendResult
    ) -> Literal["fast_accept", "slow_verify", "fail_closed"]:
        if result.coverage is None or result.selection is None:
            return "fail_closed"
        coverage = (
            result.coverage.calibrated
            if result.coverage.calibrated is not None
            else result.coverage.raw
        )
        selection = (
            result.selection.confidence_calibrated
            if result.selection.confidence_calibrated is not None
            else result.selection.confidence_raw
        )
        if selection is None:
            return "fail_closed"
        if coverage >= self.fast_coverage and selection >= self.fast_selection:
            return "fast_accept"
        return "slow_verify"


def conformal_coverage_threshold(
    adequate_probabilities: Sequence[float], *, miscoverage: float = 0.1
) -> float:
    if not adequate_probabilities or not 0 < miscoverage < 1:
        raise ValueError("adequate probabilities and a miscoverage value in (0, 1) are required")
    ordered = sorted(adequate_probabilities)
    index = max(0, math.ceil((len(ordered) + 1) * miscoverage) - 1)
    return ordered[min(index, len(ordered) - 1)]


def risk_latency_token_curve(rows: Sequence[dict[str, float | bool]]) -> list[dict[str, float]]:
    if not rows:
        return []
    thresholds = sorted({float(row["coverage_threshold"]) for row in rows})
    curve = []
    for threshold in thresholds:
        members = [row for row in rows if float(row["coverage_threshold"]) == threshold]
        errors = Counter(bool(row["error"]) for row in members)
        curve.append(
            {
                "coverage_threshold": threshold,
                "risk": errors[True] / len(members),
                "mean_latency_ms": sum(float(row["latency_ms"]) for row in members) / len(members),
                "mean_tokens": sum(float(row["tokens"]) for row in members) / len(members),
            }
        )
    return curve
