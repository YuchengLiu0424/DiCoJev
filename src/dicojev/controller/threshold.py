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
        focus_candidate_ids: tuple[str, ...] = (),
        requested_new_candidates: int = 1,
    ) -> ControllerDecision:
        signal = FeedbackSignal(
            code=code,
            evidence_refs=evidence_refs,
            focus_candidate_ids=focus_candidate_ids,
            details=(
                {"requested_new_candidates": requested_new_candidates}
                if generation_relevant
                else {}
            ),
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
        self,
        result: DecisionBackendResult,
        *,
        round_index: int,
        expansions_remaining: int,
        candidate_budget_remaining: int | None = None,
        latency_budget_remaining: float | None = None,
        compute_budget_remaining: float | None = None,
    ) -> ControllerDecision:
        can_expand = (
            expansions_remaining > 0
            and candidate_budget_remaining != 0
            and (latency_budget_remaining is None or latency_budget_remaining > 0)
            and (compute_budget_remaining is None or compute_budget_remaining >= 2)
        )
        blocked_budget = "expansion_budget_exhausted"
        if candidate_budget_remaining == 0:
            blocked_budget = "candidate_budget_exhausted"
        elif latency_budget_remaining is not None and latency_budget_remaining <= 0:
            blocked_budget = "latency_budget_exhausted"
        elif compute_budget_remaining is not None and compute_budget_remaining < 2:
            blocked_budget = "compute_budget_exhausted"
        requested = 1 if candidate_budget_remaining is None else min(2, candidate_budget_remaining)
        coverage, selection = result.coverage, result.selection
        if coverage is None or selection is None:
            return self._decision(
                MetaAction.ESCALATE,
                FeedbackCode.INSUFFICIENT_INFORMATION,
                "missing_evidence",
                round_index,
            )
        unavailable = tuple(
            candidate_id
            for candidate_id, quality in result.candidate_quality.items()
            if not quality.tool_available
        )
        violations = tuple(
            candidate_id
            for candidate_id, quality in result.candidate_quality.items()
            if not quality.constraint_compliant
        )
        redundant = tuple(
            candidate_id
            for candidate_id, quality in result.candidate_quality.items()
            if quality.redundancy_group is not None
        )
        invalid = tuple(
            candidate_id
            for candidate_id, quality in result.candidate_quality.items()
            if not quality.syntactically_valid
        )
        quality_issue = None
        selected_id = selection.selected_id
        all_quality = result.candidate_quality
        if invalid and (selected_id in invalid or len(invalid) == len(all_quality)):
            quality_issue = (
                FeedbackCode.CONSTRAINT_FAILURE,
                "invalid_candidate_format",
                invalid,
            )
        elif unavailable and (selected_id in unavailable or len(unavailable) == len(all_quality)):
            quality_issue = (FeedbackCode.TOOL_MISMATCH, "unavailable_candidate_tool", unavailable)
        elif violations and (selected_id in violations or len(violations) == len(all_quality)):
            quality_issue = (
                FeedbackCode.CONSTRAINT_FAILURE,
                "candidate_constraint_violation",
                violations,
            )
        elif redundant and len(redundant) == len(all_quality):
            quality_issue = (FeedbackCode.REDUNDANT_SET, "candidate_set_redundant", redundant)
        if quality_issue is not None:
            code, reason, candidate_ids = quality_issue
            if can_expand:
                return self._decision(
                    MetaAction.EXPAND,
                    code,
                    reason,
                    round_index,
                    generation_relevant=True,
                    evidence_refs=("candidate_quality",),
                    focus_candidate_ids=candidate_ids,
                    requested_new_candidates=requested,
                )
            return self._decision(
                MetaAction.ABSTAIN,
                code,
                f"{reason}:{blocked_budget}",
                round_index,
                evidence_refs=("candidate_quality",),
                focus_candidate_ids=candidate_ids,
            )
        if coverage.raw < self.min_coverage:
            if can_expand:
                return self._decision(
                    MetaAction.EXPAND,
                    FeedbackCode.MISSING_ACTION,
                    "coverage_below_threshold",
                    round_index,
                    generation_relevant=True,
                    evidence_refs=("coverage.raw",),
                    requested_new_candidates=requested,
                )
            return self._decision(
                MetaAction.ABSTAIN,
                FeedbackCode.MISSING_ACTION,
                f"coverage_low:{blocked_budget}",
                round_index,
                evidence_refs=("coverage.raw",),
            )
        if (
            selection.selected_id is None
            or selection.selected_id == "N"
            or selection.confidence_raw is None
            or selection.confidence_raw < self.min_selection
        ):
            if can_expand:
                return self._decision(
                    MetaAction.EXPAND,
                    FeedbackCode.AMBIGUOUS_SELECTION,
                    "selection_below_threshold",
                    round_index,
                    generation_relevant=True,
                    evidence_refs=("selection.confidence_raw",),
                    requested_new_candidates=requested,
                )
            return self._decision(
                MetaAction.ABSTAIN,
                FeedbackCode.AMBIGUOUS_SELECTION,
                f"selection_below_threshold:{blocked_budget}",
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
