"""Deterministic normalized backend for offline tests."""

from collections.abc import Iterable

from ..schemas import (
    BackendCapabilities,
    Candidate,
    DecisionBackendResult,
    DecisionSpec,
    MultimodalState,
)


class MockDecisionBackend:
    capabilities = BackendCapabilities()

    def __init__(
        self,
        results: Iterable[DecisionBackendResult | Exception],
        *,
        capabilities: BackendCapabilities | None = None,
    ) -> None:
        self._results = iter(results)
        self.capabilities = capabilities or type(self).capabilities
        self.calls: list[tuple[MultimodalState, DecisionSpec, list[Candidate]]] = []

    async def decide(
        self, state: MultimodalState, spec: DecisionSpec, candidates: list[Candidate]
    ) -> DecisionBackendResult:
        self.calls.append((state, spec, list(candidates)))
        result = next(self._results)
        if isinstance(result, Exception):
            raise result
        return result
