"""CPU-only reference closed loop."""

from __future__ import annotations

from time import perf_counter

from ..protocols import (
    CandidateGenerator,
    DecisionBackend,
    EscalationTarget,
    FeedbackCompiler,
    RiskController,
)
from ..schemas import (
    ControllerDecision,
    DecisionBackendResult,
    DecisionRequest,
    DecisionResponse,
    EscalationRequest,
    FeedbackBundle,
    FeedbackCode,
    FeedbackSignal,
    LoopContext,
    MetaAction,
    TelemetryEvent,
)
from .core import (
    CandidateRegistry,
    inject_nota,
    merge_candidates,
    validate_backend_result,
    validate_candidates,
)


class DecisionOrchestrator:
    def __init__(
        self,
        generator: CandidateGenerator,
        backend: DecisionBackend,
        controller: RiskController,
        feedback_compiler: FeedbackCompiler,
        escalation_target: EscalationTarget | None = None,
    ) -> None:
        self.generator = generator
        self.backend = backend
        self.controller = controller
        self.feedback_compiler = feedback_compiler
        self.escalation_target = escalation_target

    @staticmethod
    def _failure(round_index: int, reason: str) -> ControllerDecision:
        bundle = FeedbackBundle(
            primary=FeedbackSignal(code=FeedbackCode.INSUFFICIENT_INFORMATION),
            source_round=round_index,
            controller_reason_code=reason,
            generation_relevant=False,
        )
        return ControllerDecision(action=MetaAction.ESCALATE, reason_code=reason, feedback=bundle)

    async def run(self, request: DecisionRequest) -> DecisionResponse:
        registry = CandidateRegistry()
        candidates = []
        trace: list[TelemetryEvent] = []
        context = None
        backend_result = DecisionBackendResult(backend="unavailable")
        decision = self._failure(0, "not_started")

        for round_index in range(request.budget.max_expansions + 1):
            generation_ms = 0.0
            feedback_ms = 0.0
            try:
                generation_started = perf_counter()
                spec = await self.generator.generate(request, context)
                generation_ms = (perf_counter() - generation_started) * 1000
                new = registry.register(spec.candidates, round_index)
                candidates = merge_candidates(candidates, new)
                validate_candidates(candidates, request)
                if request.state.images and not self.backend.capabilities.supports_images:
                    raise ValueError("backend does not support image state")
                backend_candidates = (
                    inject_nota(candidates)
                    if self.backend.capabilities.supports_nota
                    else list(candidates)
                )
                backend_result = await self.backend.decide(request.state, spec, backend_candidates)
                validate_backend_result(
                    backend_result,
                    backend_candidates,
                    supports_nota=self.backend.capabilities.supports_nota,
                )
                decision = await self.controller.decide(
                    backend_result,
                    round_index=round_index,
                    expansions_remaining=request.budget.max_expansions - round_index,
                )
            except Exception as error:  # noqa: BLE001 - normalize component boundaries fail-closed
                backend_result = DecisionBackendResult(
                    backend="unavailable",
                    diagnostics={"error_type": type(error).__name__},
                )
                decision = self._failure(round_index, f"component_failure:{type(error).__name__}")

            feedback_codes = (
                decision.feedback.primary.code,
                *(item.code for item in decision.feedback.secondary),
            )
            trace.append(
                TelemetryEvent(
                    round_index=round_index,
                    candidate_ids=tuple(item.id or "" for item in candidates),
                    semantic_candidate_count=len(candidates),
                    backend=backend_result.backend,
                    coverage_raw=backend_result.coverage.raw if backend_result.coverage else None,
                    coverage_calibrated=(
                        backend_result.coverage.calibrated if backend_result.coverage else None
                    ),
                    selection_raw=(
                        backend_result.selection.confidence_raw
                        if backend_result.selection
                        else None
                    ),
                    selection_calibrated=(
                        backend_result.selection.confidence_calibrated
                        if backend_result.selection
                        else None
                    ),
                    feedback_codes=feedback_codes,
                    controller_action=decision.action,
                    controller_reason_code=decision.reason_code,
                    latency_ms={
                        "generation": generation_ms,
                        "backend": backend_result.latency_ms,
                        "feedback_compilation": feedback_ms,
                    },
                )
            )
            if decision.action is not MetaAction.EXPAND:
                break
            try:
                feedback_started = perf_counter()
                compiled = await self.feedback_compiler.compile(decision.feedback)
                feedback_ms = (perf_counter() - feedback_started) * 1000
            except Exception as error:  # noqa: BLE001 - normalize compiler boundary fail-closed
                decision = self._failure(
                    round_index, f"feedback_compilation_failure:{type(error).__name__}"
                )
                trace[-1] = trace[-1].model_copy(
                    update={
                        "controller_action": decision.action,
                        "controller_reason_code": decision.reason_code,
                    }
                )
                break
            trace[-1] = trace[-1].model_copy(
                update={
                    "feedback_serialized_bytes": compiled.serialized_bytes,
                    "feedback_referenced_candidate_ids": compiled.referenced_candidate_count,
                    "compiled_feedback_prompt_tokens": compiled.prompt_tokens,
                    "latency_ms": {
                        **trace[-1].latency_ms,
                        "feedback_compilation": feedback_ms,
                    },
                }
            )
            context = LoopContext(
                round_index=round_index + 1,
                prior_candidates=tuple(candidates),
                latest_feedback=decision.feedback,
                feedback_history=tuple(code for event in trace for code in event.feedback_codes),
                generation_feedback=compiled,
                remaining_candidate_budget=max(0, request.budget.max_candidates - len(candidates)),
                remaining_expansion_budget=request.budget.max_expansions - round_index - 1,
                remaining_latency_ms=request.budget.latency_ms,
                remaining_compute_units=request.budget.compute_units,
            )

        selected = next(
            (item for item in candidates if item.id == decision.selected_candidate_id), None
        )
        escalation_result = None
        if decision.action is MetaAction.ESCALATE and self.escalation_target is not None:
            try:
                escalation_result = await self.escalation_target.escalate(
                    EscalationRequest(
                        request=request,
                        candidates=tuple(candidates),
                        reason_code=decision.reason_code,
                    )
                )
            except Exception as error:  # noqa: BLE001 - unavailable escalation remains fail-closed
                decision = self._failure(
                    decision.feedback.source_round,
                    f"escalation_unavailable:{type(error).__name__}",
                )
        return DecisionResponse(
            action=decision.action,
            selected_candidate=selected,
            candidates=tuple(candidates),
            controller=decision,
            backend_result=backend_result,
            feedback=decision.feedback,
            trace=tuple(trace),
            escalation_result=escalation_result,
        )
