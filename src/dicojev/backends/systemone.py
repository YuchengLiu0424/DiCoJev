"""Jev-compatible System One HTTP adapters and wire normalization."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from time import perf_counter
from typing import Any

import httpx

from ..errors import BackendUnavailable, ConfigurationError, MalformedProviderResponse
from ..schemas import (
    BackendCapabilities,
    Candidate,
    CoverageScore,
    DecisionBackendResult,
    DecisionSpec,
    MultimodalState,
    SelectionScore,
)


def compile_systemone_request(
    state: MultimodalState,
    spec: DecisionSpec,
    candidates: list[Candidate],
    *,
    model: str,
) -> dict[str, Any]:
    semantic = [candidate for candidate in candidates if not candidate.synthetic]
    wire_state: dict[str, Any] = {
        "observation": state.text,
        "structured": state.structured,
        "task": spec.task,
        "constraints": list(spec.constraints),
        "candidates": {candidate.id: candidate.action for candidate in semantic},
    }
    return {
        "model": model,
        "state": wire_state,
        "questions": {
            "coverage": {
                "type": "noul",
                "instructions": spec.coverage_instruction,
                "criteria": {
                    "true": "At least one semantic candidate is acceptable.",
                    "false": "No semantic candidate is acceptable.",
                },
            },
            "selection": {
                "type": "choice",
                "instructions": spec.selection_instruction,
                "criteria": {candidate.id: candidate.action for candidate in candidates},
            },
        },
    }


def normalize_systemone_response(
    payload: dict[str, Any], *, backend: str, latency_ms: float
) -> DecisionBackendResult:
    result = payload.get("result", payload)
    try:
        answers = result["answers"]
        coverage = answers["coverage"]
        selection = answers["selection"]
        if coverage.get("type") != "noul" or selection.get("type") != "choice":
            raise KeyError("answer type mismatch")
        selected_id = selection["choice"]
        probabilities = selection["probabilities"]
        confidence = selection["confidence"]
        q_cov = coverage["noul"]
    except (KeyError, TypeError) as error:
        raise MalformedProviderResponse("malformed System One response") from error
    raw_probability_sum = sum(probabilities.values()) if isinstance(probabilities, dict) else None
    if isinstance(probabilities, dict) and probabilities and raw_probability_sum:
        rounding_tolerance = max(1e-6, len(probabilities) * 5e-5 + 1e-12)
        if abs(raw_probability_sum - 1.0) <= rounding_tolerance:
            probabilities = {
                label: value / raw_probability_sum for label, value in probabilities.items()
            }
    diagnostics = {
        "model": payload.get("model"),
        "usage": result.get("usage", payload.get("usage", {})),
        "provider_elapsed_ms": result.get("elapsedMs", payload.get("elapsedMs")),
        "provider_diagnostics": result.get("diagnostics", payload.get("diagnostics", {})),
        "selection_probability_sum_raw": raw_probability_sum,
    }
    try:
        return DecisionBackendResult(
            backend=backend,
            coverage=CoverageScore(raw=q_cov, method="noul_probability"),
            selection=SelectionScore(
                selected_id=selected_id,
                probabilities=probabilities,
                confidence_raw=confidence,
            ),
            diagnostics=diagnostics,
            latency_ms=latency_ms,
        )
    except ValueError as error:
        raise MalformedProviderResponse("invalid System One probabilities") from error


class _SystemOneBackend:
    backend_name = "systemone"
    capabilities = BackendCapabilities(requires_network=True, supports_nota=True)

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 30,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        label_validator: Callable[[str], bool] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key
        self.transport = transport
        self.label_validator = label_validator

    async def decide(
        self, state: MultimodalState, spec: DecisionSpec, candidates: list[Candidate]
    ) -> DecisionBackendResult:
        if state.images and not self.capabilities.supports_images:
            raise BackendUnavailable(f"{self.backend_name} does not support images")
        if self.label_validator is not None:
            invalid = [item.id for item in candidates if not self.label_validator(item.id or "")]
            if invalid:
                raise BackendUnavailable(f"invalid single-token labels: {invalid}")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        started = perf_counter()
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
                headers=headers,
            ) as client:
                response = await client.post(
                    "/v1/systemone",
                    json=compile_systemone_request(state, spec, candidates, model=self.model),
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise BackendUnavailable(f"{self.backend_name} unavailable") from error
        latency_ms = (perf_counter() - started) * 1000
        return normalize_systemone_response(
            payload, backend=self.backend_name, latency_ms=latency_ms
        )


class JevCloudBackend(_SystemOneBackend):
    backend_name = "jev_cloud"
    capabilities = BackendCapabilities(
        requires_network=True, requires_api_key=True, supports_nota=True
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.typesafe.ai",
        model: str = "jev-latest",
        timeout_seconds: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        key = api_key or os.getenv("JEV_API_KEY")
        if not key:
            raise ConfigurationError("JEV_API_KEY is required for jev_cloud")
        super().__init__(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            api_key=key,
            transport=transport,
        )


class DjevLocalBackend(_SystemOneBackend):
    backend_name = "djev_local"
    capabilities = BackendCapabilities(
        requires_network=True,
        requires_single_token_labels=True,
        supports_nota=True,
    )

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8011",
        model: str = "dgemma",
        timeout_seconds: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
        label_validator: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            transport=transport,
            label_validator=label_validator or (lambda label: bool(re.fullmatch(r"[A-Z]+", label))),
        )


class LayaLocalBackend(_SystemOneBackend):
    """Local open-weight System One backend using Laya's Jev-compatible API."""

    backend_name = "laya_local"
    capabilities = BackendCapabilities(requires_network=True, supports_nota=True)

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8011",
        model: str = "english",
        timeout_seconds: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
