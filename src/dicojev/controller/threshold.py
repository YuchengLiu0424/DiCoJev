"""Fail-closed deterministic reference controller."""

from ..schemas import (
    ControllerDecision,
    DecisionBackendResult,
    FeedbackBundle,
    FeedbackCode,
    FeedbackSignal,
    MetaAction,
)


class ThresholdRiskController:
    def __init__(self, min_coverage: float = 0.75, min_selection: float = 0.70) -> None:
        self.min_coverage = min_coverage
        self.min_selection = min_selection

    def _decision(
        self,
        action: MetaAction,
        code: FeedbackCode,
        reason: str,
        round_index: int,
        *,
        selected_id: str | None = None,
        generation_relevant: bool = False,
        evidence_refs: tuple[str, ...] = (),
    ) -> ControllerDecision:
        signal = FeedbackSignal(
            code=code,
            evidence_refs=evidence_refs,
            details={"requested_new_candidates": 1} if generation_relevant else {},
        )
        bundle = FeedbackBundle(
            primary=signal,
            source_round=round_index,
            controller_reason_code=reason,
            generation_relevant=generation_relevant,
        )
        return ControllerDecision(
            action=action,
            reason_code=reason,
            feedback=bundle,
            selected_candidate_id=selected_id,
        )
    async def decide(
        self, result: DecisionBackendResult, *, round_index: int, expansions_remaining: int
    ) -> ControllerDecision:
        coverage, selection = result.coverage, result.selection
        if coverage is None or selection is None:
            return self._decision(
                MetaAction.ESCALATE,
                FeedbackCode.INSUFFICIENT_INFORMATION,
                "missing_evidence",
                round_index,
            )
        if coverage.raw < self.min_coverage:
            if expansions_remaining > 0:
                return self._decision(
                    MetaAction.EXPAND,
                    FeedbackCode.MISSING_ACTION,
                    "coverage_below_threshold",
                    round_index,
                    generation_relevant=True,
                    evidence_refs=("coverage.raw",),
                )
            return self._decision(
                MetaAction.ABSTAIN,
                FeedbackCode.MISSING_ACTION,
                "coverage_low_budget_exhausted",
                round_index,
                evidence_refs=("coverage.raw",),
            )
        if (
            selection.selected_id is None
            or selection.selected_id == "N"
            or selection.confidence_raw is None
            or selection.confidence_raw < self.min_selection
        ):
            return self._decision(
                MetaAction.ABSTAIN,
                FeedbackCode.AMBIGUOUS_SELECTION,
                "selection_below_threshold",
                round_index,
                evidence_refs=("selection.confidence_raw",),
            )
        return self._decision(
            MetaAction.ACT,
            FeedbackCode.ADEQUATE,
            "thresholds_passed",
            round_index,
            selected_id=selection.selected_id,
            evidence_refs=("coverage.raw", "selection.confidence_raw"),
        )
