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

    def __init__(self, results: Iterable[DecisionBackendResult | Exception]) -> None:
        self._results = iter(results)

    async def decide(
        self, state: MultimodalState, spec: DecisionSpec, candidates: list[Candidate]
    ) -> DecisionBackendResult:
        del state, spec, candidates
        result = next(self._results)
        if isinstance(result, Exception):
            raise result
        return result
