"""CPU-only reference closed loop."""

from __future__ import annotations

from time import perf_counter

from ..errors import BudgetExhausted, CapabilityMismatch
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
    EscalationResult,
    FeedbackBundle,
    FeedbackCode,
    FeedbackSignal,
    LoopContext,
    MetaAction,
    TelemetryEvent,
)
from .core import (
    CandidateRegistry,
    evaluate_candidate_quality,
    inject_nota,
    merge_candidate_quality,
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

    @staticmethod
    def _budget_stop(round_index: int, reason: str) -> ControllerDecision:
        bundle = FeedbackBundle(
            primary=FeedbackSignal(code=FeedbackCode.INSUFFICIENT_INFORMATION),
            source_round=round_index,
            controller_reason_code=reason,
            generation_relevant=False,
        )
        return ControllerDecision(action=MetaAction.ABSTAIN, reason_code=reason, feedback=bundle)

    async def run(self, request: DecisionRequest) -> DecisionResponse:
        run_started = perf_counter()
        registry = CandidateRegistry()
        candidates = []
        trace: list[TelemetryEvent] = []
        context = None
        backend_result = DecisionBackendResult(backend="unavailable")
        decision = self._failure(0, "not_started")
        compute_used = 0.0

        for round_index in range(request.budget.max_expansions + 1):
            generation_ms = 0.0
            feedback_ms = 0.0
            generation_units = 0.0
            backend_units = 0.0
            try:
                elapsed_ms = (perf_counter() - run_started) * 1000
                if (
                    request.budget.latency_ms is not None
                    and elapsed_ms >= request.budget.latency_ms
                ):
                    raise BudgetExhausted("latency_budget_exhausted")
                if (
                    request.budget.compute_units is not None
                    and request.budget.compute_units - compute_used < 2
                ):
                    raise BudgetExhausted("compute_budget_exhausted")
                generator_capabilities = getattr(self.generator, "capabilities", None)
                if request.state.images and (
                    generator_capabilities is None
                    or not generator_capabilities.supports_images
                    or not generator_capabilities.supports_native_multimodal
                ):
                    raise CapabilityMismatch("generator_native_multimodal_unsupported")
                generation_started = perf_counter()
                spec = await self.generator.generate(request, context)
                generation_ms = (perf_counter() - generation_started) * 1000
                compute_used += 1
                generation_units = 1.0
                new = registry.register(spec.candidates, round_index)
                candidates = merge_candidates(candidates, new)
                validate_candidates(candidates, request)
                quality = evaluate_candidate_quality(candidates, request)
                if request.state.images and (
                    not self.backend.capabilities.supports_images
                    or not self.backend.capabilities.supports_native_multimodal
                ):
                    raise CapabilityMismatch("backend_native_multimodal_unsupported")
                backend_candidates = (
                    inject_nota(candidates)
                    if self.backend.capabilities.supports_nota
                    else list(candidates)
                )
                backend_result = await self.backend.decide(request.state, spec, backend_candidates)
                compute_used += 1
                backend_units = 1.0
                validate_backend_result(
                    backend_result,
                    backend_candidates,
                    supports_nota=self.backend.capabilities.supports_nota,
                )
                backend_result = backend_result.model_copy(
                    update={
                        "candidate_quality": merge_candidate_quality(
                            quality, backend_result.candidate_quality
                        )
                    }
                )
                elapsed_ms = (perf_counter() - run_started) * 1000
                remaining_latency = (
                    None
                    if request.budget.latency_ms is None
                    else max(0.0, request.budget.latency_ms - elapsed_ms)
                )
                remaining_compute = (
                    None
                    if request.budget.compute_units is None
                    else max(0.0, request.budget.compute_units - compute_used)
                )
                decision = await self.controller.decide(
                    backend_result,
                    round_index=round_index,
                    expansions_remaining=request.budget.max_expansions - round_index,
                    candidate_budget_remaining=max(
                        0, request.budget.max_candidates - len(candidates)
                    ),
                    latency_budget_remaining=remaining_latency,
                    compute_budget_remaining=remaining_compute,
                )
            except BudgetExhausted as error:
                backend_result = DecisionBackendResult(backend="unavailable")
                decision = self._budget_stop(round_index, str(error))
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
            elapsed_ms = (perf_counter() - run_started) * 1000
            remaining_latency = (
                None
                if request.budget.latency_ms is None
                else max(0.0, request.budget.latency_ms - elapsed_ms)
            )
            remaining_compute = (
                None
                if request.budget.compute_units is None
                else max(0.0, request.budget.compute_units - compute_used)
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
                    selected_candidate_id=(
                        backend_result.selection.selected_id if backend_result.selection else None
                    ),
                    selection_probabilities=(
                        backend_result.selection.probabilities if backend_result.selection else {}
                    ),
                    feedback_codes=feedback_codes,
                    controller_action=decision.action,
                    controller_reason_code=decision.reason_code,
                    latency_ms={
                        "generation": generation_ms,
                        "backend": backend_result.latency_ms,
                        "feedback_compilation": feedback_ms,
                    },
                    compute_units={
                        "generation": generation_units,
                        "backend": backend_units,
                    },
                    candidate_quality=backend_result.candidate_quality,
                    remaining_candidate_budget=max(
                        0, request.budget.max_candidates - len(candidates)
                    ),
                    remaining_expansion_budget=max(
                        0,
                        request.budget.max_expansions
                        - round_index
                        - (1 if decision.action is MetaAction.EXPAND else 0),
                    ),
                    remaining_latency_ms=remaining_latency,
                    remaining_compute_units=remaining_compute,
                    image_count=len(request.state.images),
                )
            )
            if decision.action is not MetaAction.EXPAND:
                break
            try:
                feedback_started = perf_counter()
                compiled = await self.feedback_compiler.compile(decision.feedback)
                feedback_ms = (perf_counter() - feedback_started) * 1000
                if request.budget.latency_ms is not None:
                    remaining_latency = max(
                        0.0,
                        request.budget.latency_ms - (perf_counter() - run_started) * 1000,
                    )
            except Exception as error:  # noqa: BLE001 - normalize compiler boundary fail-closed
                decision = self._failure(
                    round_index, f"feedback_compilation_failure:{type(error).__name__}"
                )
                trace[-1] = trace[-1].model_copy(
                    update={
                        "controller_action": decision.action,
                        "controller_reason_code": decision.reason_code,
                        "feedback_codes": (decision.feedback.primary.code,),
                    }
                )
                break
            trace[-1] = trace[-1].model_copy(
                update={
                    "feedback_serialized_bytes": compiled.serialized_bytes,
                    "feedback_referenced_candidate_ids": compiled.referenced_candidate_count,
                    "compiled_feedback_prompt_tokens": compiled.prompt_tokens,
                    "remaining_latency_ms": remaining_latency,
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
                remaining_latency_ms=remaining_latency,
                remaining_compute_units=remaining_compute,
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
                escalation_result = EscalationResult(
                    target=type(self.escalation_target).__name__,
                    status="unavailable",
                    message=f"unavailable:{type(error).__name__}",
                )
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
            total_latency_ms=(perf_counter() - run_started) * 1000,
            total_compute_units=compute_used,
            escalation_result=escalation_result,
        )
