"""Unified v5 runtime, action boundary, and end-to-end agent facade."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any

from .backends import LladaHTTPNativeReadRuntime, NativeDLMDecisionBackend
from .generator import LladaGenerator
from .schemas import (
    ActionExecution,
    BackendCapabilities,
    Candidate,
    DecisionRequest,
    DecisionResponse,
    EnvironmentTransition,
    GeneratorCapabilities,
    MetaAction,
    MultimodalState,
)


class UnifiedLladaRuntime:
    """One local server/process surface for candidate generation and structured reads."""

    generator_capabilities = GeneratorCapabilities(
        supports_text=True,
        supports_images=True,
        supports_native_multimodal=True,
    )
    backend_capabilities = BackendCapabilities(
        supports_text=True,
        supports_images=True,
        supports_native_multimodal=True,
        supports_binary_coverage=True,
        supports_choice_distribution=True,
        supports_score=True,
        requires_single_token_labels=True,
        supports_nota=True,
    )

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8002",
        model: str = "llada-v-local",
        timeout_seconds: float = 600,
        transport=None,
        batch_reads: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.generator = LladaGenerator(
            base_url=self.base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
        self.reader = LladaHTTPNativeReadRuntime(
            base_url=self.base_url,
            timeout_seconds=timeout_seconds,
            transport=transport,
            batch_reads=batch_reads,
        )
        self.supports_batch_reads = self.reader.supports_batch_reads

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "shared_endpoint": self.base_url,
            "generation_usage": self.generator.last_usage,
            "generation_latency_ms": self.generator.last_latency_ms,
            "reads": self.reader.diagnostics,
        }

    async def generate(self, request, context=None):
        return await self.generator.generate(request, context)

    async def read(self, request):
        return await self.reader.read(request)

    async def read_many(self, requests):
        return await self.reader.read_many(requests)

    def decision_backend(self) -> NativeDLMDecisionBackend:
        return NativeDLMDecisionBackend(self, runtime_name="unified-llada-v")


class AllowlistedToolExecutor:
    """Explicit execution boundary; undeclared tools and unbound handlers fail closed."""

    def __init__(self, handlers: Mapping[str, Callable[..., Any]]) -> None:
        self.handlers = dict(handlers)

    async def execute(
        self, candidate: Candidate, state: MultimodalState
    ) -> tuple[ActionExecution, MultimodalState]:
        started = perf_counter()
        if candidate.tool is None:
            return (
                ActionExecution(
                    candidate_id=candidate.id or "",
                    status="not_requested",
                    latency_ms=(perf_counter() - started) * 1000,
                ),
                state,
            )
        handler = self.handlers.get(candidate.tool)
        if handler is None:
            return (
                ActionExecution(
                    candidate_id=candidate.id or "",
                    tool=candidate.tool,
                    status="rejected",
                    error_code="tool_not_allowlisted",
                    latency_ms=(perf_counter() - started) * 1000,
                ),
                state,
            )
        try:
            value = handler(state, dict(candidate.arguments_hint))
            value = await value if inspect.isawaitable(value) else value
            if not isinstance(value, tuple) or len(value) != 2:
                raise TypeError("tool handler must return (result, state_after)")
            result, state_after = value
            if not isinstance(result, dict) or not isinstance(state_after, MultimodalState):
                raise TypeError("tool handler returned invalid result or state")
            return (
                ActionExecution(
                    candidate_id=candidate.id or "",
                    tool=candidate.tool,
                    status="executed",
                    result=result,
                    latency_ms=(perf_counter() - started) * 1000,
                ),
                state_after,
            )
        except Exception as error:  # noqa: BLE001 - execution boundary normalizes failures
            return (
                ActionExecution(
                    candidate_id=candidate.id or "",
                    tool=candidate.tool,
                    status="failed",
                    error_code=type(error).__name__,
                    latency_ms=(perf_counter() - started) * 1000,
                ),
                state,
            )


class AgentRuntime:
    """Run the feedback harness and, only after ACT, cross the execution boundary."""

    def __init__(self, orchestrator, executor=None) -> None:
        self.orchestrator = orchestrator
        self.executor = executor

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        response = await self.orchestrator.run(request)
        if response.action is not MetaAction.ACT or response.selected_candidate is None:
            return response
        if self.executor is None:
            execution = ActionExecution(
                candidate_id=response.selected_candidate.id or "",
                tool=response.selected_candidate.tool,
                status="not_requested",
            )
            state_after = request.state
        else:
            execution, state_after = await self.executor.execute(
                response.selected_candidate, request.state
            )
        transition = EnvironmentTransition(
            action=execution,
            state_before=dict(request.state.structured),
            state_after=dict(state_after.structured),
        )
        return response.model_copy(update={"execution_trace": (transition,)})
