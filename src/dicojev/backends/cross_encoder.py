"""Generate-then-rank baseline with independent set-level coverage."""

from __future__ import annotations

import inspect
import math
from collections.abc import Awaitable, Callable, Sequence
from time import perf_counter

from ..errors import BackendUnavailable
from ..schemas import (
    BackendCapabilities,
    Candidate,
    CoverageScore,
    DecisionBackendResult,
    DecisionSpec,
    MultimodalState,
    SelectionScore,
)

SelectionScorer = Callable[
    [MultimodalState, DecisionSpec, list[Candidate]], Sequence[float] | Awaitable[Sequence[float]]
]
CoverageEstimator = Callable[
    [MultimodalState, DecisionSpec, list[Candidate]],
    tuple[float, str] | Awaitable[tuple[float, str]],
]


async def _resolve(value):
    return await value if inspect.isawaitable(value) else value


class CrossEncoderDecisionBackend:
    capabilities = BackendCapabilities(
        supports_nota=False,
        supports_binary_coverage=True,
        supports_choice_distribution=True,
    )

    def __init__(
        self,
        scorer: SelectionScorer,
        coverage_estimator: CoverageEstimator,
        *,
        model_name: str = "configured-cross-encoder",
    ) -> None:
        self.scorer = scorer
        self.coverage_estimator = coverage_estimator
        self.model_name = model_name

    async def decide(
        self, state: MultimodalState, spec: DecisionSpec, candidates: list[Candidate]
    ) -> DecisionBackendResult:
        if state.images:
            raise BackendUnavailable("cross_encoder v1 baseline supports text only")
        semantic = [item for item in candidates if not item.synthetic]
        if not semantic:
            raise BackendUnavailable("cross_encoder requires semantic candidates")
        started = perf_counter()
        try:
            logits = list(await _resolve(self.scorer(state, spec, semantic)))
            coverage_raw, coverage_method = await _resolve(
                self.coverage_estimator(state, spec, semantic)
            )
        except Exception as error:
            raise BackendUnavailable("cross_encoder scoring failed") from error
        if len(logits) != len(semantic) or not all(math.isfinite(item) for item in logits):
            raise BackendUnavailable("cross_encoder returned malformed logits")
        maximum = max(logits)
        weights = [math.exp(item - maximum) for item in logits]
        total = sum(weights)
        probabilities = {
            candidate.id: weight / total
            for candidate, weight in zip(semantic, weights, strict=True)
        }
        selected_id = max(probabilities, key=probabilities.__getitem__)
        return DecisionBackendResult(
            backend="cross_encoder",
            coverage=CoverageScore(raw=coverage_raw, method=coverage_method),
            selection=SelectionScore(
                selected_id=selected_id,
                probabilities=probabilities,
                confidence_raw=probabilities[selected_id],
            ),
            diagnostics={
                "selection_model": self.model_name,
                "coverage_method": coverage_method,
            },
            latency_ms=(perf_counter() - started) * 1000,
        )


class SentenceTransformersScorer:
    """Optional lazy adapter; sentence-transformers is never imported by core package import."""

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as error:
            raise BackendUnavailable(
                "install dicojev[cross-encoder] to use SentenceTransformersScorer"
            ) from error
        self.model = CrossEncoder(model_name)

    def __call__(
        self, state: MultimodalState, spec: DecisionSpec, candidates: list[Candidate]
    ) -> Sequence[float]:
        query = f"{state.text}\nGoal: {spec.task}"
        return self.model.predict([(query, candidate.action) for candidate in candidates]).tolist()
