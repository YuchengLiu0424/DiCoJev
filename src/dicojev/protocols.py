"""Async project-level component protocols."""

from typing import Protocol

from .schemas import (
    BackendCapabilities,
    Candidate,
    ControllerDecision,
    DecisionBackendResult,
    DecisionRequest,
    DecisionSpec,
    EscalationRequest,
    FeedbackBundle,
    GenerationFeedback,
    LoopContext,
    MultimodalState,
)


class CandidateGenerator(Protocol):
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
        self, result: DecisionBackendResult, *, round_index: int, expansions_remaining: int
    ) -> ControllerDecision: ...


class FeedbackCompiler(Protocol):
    async def compile(self, feedback: FeedbackBundle) -> GenerationFeedback: ...


class EscalationTarget(Protocol):
    async def escalate(self, request: EscalationRequest) -> str: ...
