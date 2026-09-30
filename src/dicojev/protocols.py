"""Async project-level component protocols."""

from typing import Protocol

from .schemas import (
    ActionExecution,
    BackendCapabilities,
    Candidate,
    ControllerDecision,
    DecisionBackendResult,
    DecisionRequest,
    DecisionSpec,
    EscalationRequest,
    EscalationResult,
    FeedbackBundle,
    GenerationFeedback,
    GeneratorCapabilities,
    LoopContext,
    MultimodalState,
)


class CandidateGenerator(Protocol):
    capabilities: GeneratorCapabilities

    async def generate(
        self, request: DecisionRequest, context: LoopContext | None = None
    ) -> DecisionSpec: ...


class DecisionBackend(Protocol):
    capabilities: BackendCapabilities

    async def decide(
        self, state: MultimodalState, spec: DecisionSpec, candidates: list[Candidate]
    ) -> DecisionBackendResult: ...


class RiskController(Protocol):
    async def decide(
        self,
        result: DecisionBackendResult,
        *,
        round_index: int,
        expansions_remaining: int,
        candidate_budget_remaining: int | None = None,
        latency_budget_remaining: float | None = None,
        compute_budget_remaining: float | None = None,
    ) -> ControllerDecision: ...


class FeedbackCompiler(Protocol):
    async def compile(self, feedback: FeedbackBundle) -> GenerationFeedback: ...


class EscalationTarget(Protocol):
    async def escalate(self, request: EscalationRequest) -> EscalationResult: ...


class ActionExecutor(Protocol):
    async def execute(
        self, candidate: Candidate, state: MultimodalState
    ) -> tuple[ActionExecution, MultimodalState]: ...
