"""Project-owned structured reads over an injected diffusion-language runtime."""

from __future__ import annotations

import inspect
import json
import math
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Literal, Protocol

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

_LABEL = re.compile(r"^[A-Z]$")


@dataclass(frozen=True)
class NativeReadRequest:
    """Deterministic canvas passed to a same-process native read implementation."""

    mode: Literal["coverage", "selection"]
    prompt: str
    labels: tuple[str, ...]
    state: MultimodalState


class NativeReadRuntime(Protocol):
    def read(self, request: NativeReadRequest) -> Sequence[float] | Awaitable[Sequence[float]]: ...


LabelValidator = Callable[[str], bool]


def _softmax(logits: Sequence[float]) -> list[float]:
    values = [float(value) for value in logits]
    if not values or not all(math.isfinite(value) for value in values):
        raise BackendUnavailable("native DLM returned empty or non-finite logits")
    maximum = max(values)
    weights = [math.exp(value - maximum) for value in values]
    total = sum(weights)
    return [weight / total for weight in weights]


def _candidate_block(candidates: list[Candidate]) -> str:
    return json.dumps(
        [{"label": candidate.id, "action": candidate.action} for candidate in candidates],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def build_native_read_request(
    mode: Literal["coverage", "selection"],
    state: MultimodalState,
    spec: DecisionSpec,
    candidates: list[Candidate],
) -> NativeReadRequest:
    """Construct the stable prompt/canvas contract used by native runtimes."""
    candidate_json = _candidate_block(candidates)
    state_json = json.dumps(
        state.structured, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    shared = (
        f"STATE_TEXT\n{state.text}\nSTATE_JSON\n{state_json}\nTASK\n{spec.task}\n"
        f"CANDIDATES\n{candidate_json}\n"
    )
    if mode == "coverage":
        return NativeReadRequest(
            mode=mode,
            prompt=(
                shared + f"QUESTION\n{spec.coverage_instruction}\n"
                "OUTPUT_LABEL\nChoose 1 if at least one candidate is acceptable, otherwise 0."
            ),
            labels=("0", "1"),
            state=state,
        )
    return NativeReadRequest(
        mode=mode,
        prompt=(
            shared + f"QUESTION\n{spec.selection_instruction}\n"
            "OUTPUT_LABEL\nChoose exactly one candidate label."
        ),
        labels=tuple(candidate.id or "" for candidate in candidates),
        state=state,
    )


class NativeDLMDecisionBackend:
    """Normalize binary coverage and categorical native DLM reads."""

    capabilities = BackendCapabilities(
        supports_images=True,
        supports_native_multimodal=True,
        requires_single_token_labels=True,
    )

    def __init__(
        self,
        runtime: NativeReadRuntime,
        *,
        label_validator: LabelValidator | None = None,
        runtime_name: str = "native-dlm",
    ) -> None:
        self.runtime = runtime
        self.label_validator = label_validator or (lambda label: bool(_LABEL.fullmatch(label)))
        self.runtime_name = runtime_name

    def _validate_candidates(self, candidates: list[Candidate]) -> None:
        if not candidates:
            raise BackendUnavailable("native DLM requires at least one candidate")
        labels = [candidate.id for candidate in candidates]
        if any(label is None or not self.label_validator(label) for label in labels):
            raise BackendUnavailable("native DLM candidate labels must be valid single tokens")
        if len(labels) != len(set(labels)):
            raise BackendUnavailable("native DLM candidate labels must be unique")

    async def _read(self, request: NativeReadRequest) -> list[float]:
        try:
            result = self.runtime.read(request)
            logits = list(await result if inspect.isawaitable(result) else result)
        except BackendUnavailable:
            raise
        except Exception as error:
            raise BackendUnavailable(f"{request.mode} native DLM read failed") from error
        if len(logits) != len(request.labels):
            raise BackendUnavailable(
                f"{request.mode} native DLM read returned {len(logits)} logits "
                f"for {len(request.labels)} labels"
            )
        return logits

    async def decide(
        self, state: MultimodalState, spec: DecisionSpec, candidates: list[Candidate]
    ) -> DecisionBackendResult:
        self._validate_candidates(candidates)
        started = perf_counter()
        coverage_request = build_native_read_request("coverage", state, spec, candidates)
        selection_request = build_native_read_request("selection", state, spec, candidates)
        coverage_logits = await self._read(coverage_request)
        selection_logits = await self._read(selection_request)
        coverage_probabilities = _softmax(coverage_logits)
        selection_values = _softmax(selection_logits)
        probabilities = dict(zip(selection_request.labels, selection_values, strict=True))
        selected_id = max(probabilities, key=probabilities.__getitem__)
        return DecisionBackendResult(
            backend="native_dlm",
            coverage=CoverageScore(raw=coverage_probabilities[1], method="native_binary_read"),
            selection=SelectionScore(
                selected_id=selected_id,
                probabilities=probabilities,
                confidence_raw=probabilities[selected_id],
            ),
            diagnostics={
                "runtime": self.runtime_name,
                "coverage_labels": list(coverage_request.labels),
                "coverage_logits": coverage_logits,
                "selection_labels": list(selection_request.labels),
                "selection_logits": selection_logits,
            },
            latency_ms=(perf_counter() - started) * 1000,
        )
