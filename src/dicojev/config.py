"""Configuration loading and component factories."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .backends import (
    DjevLocalBackend,
    JevCloudBackend,
    LayaLocalBackend,
    LladaHTTPNativeReadRuntime,
    MockDecisionBackend,
    NativeDLMDecisionBackend,
)
from .backends.cross_encoder import CrossEncoderDecisionBackend
from .errors import ConfigurationError
from .generator import (
    DiffusionGemmaGenerator,
    FakeCandidateGenerator,
    LladaGenerator,
    MercuryGenerator,
)


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ConfigurationError("configuration root must be a mapping")
    return payload


def create_generator(config: dict[str, Any], **dependencies: Any):
    model = config.get("model", {})
    kind = model.get("generator_kind", "fake")
    if kind == "fake":
        rounds = dependencies.get("rounds")
        if rounds is None:
            raise ConfigurationError("fake generator requires scripted rounds")
        return FakeCandidateGenerator(rounds)
    if kind == "diffusiongemma":
        return DiffusionGemmaGenerator(
            base_url=model.get("base_url", "http://127.0.0.1:8000"),
            model=model.get("generator_model", "google/diffusiongemma-26B-A4B-it"),
            timeout_seconds=model.get("timeout_seconds", 60),
            transport=dependencies.get("transport"),
        )
    if kind == "mercury":
        return MercuryGenerator(
            api_key=dependencies.get("api_key"),
            base_url=model.get("base_url", "https://api.inceptionlabs.ai/v1"),
            model=model.get("generator_model", "mercury-2.5"),
            timeout_seconds=model.get("timeout_seconds", 60),
            transport=dependencies.get("transport"),
        )
    if kind == "llada":
        return LladaGenerator(
            base_url=model.get("base_url", "http://127.0.0.1:8002"),
            model=model.get("generator_model", "llada-v-local"),
            timeout_seconds=model.get("timeout_seconds", 600),
            transport=dependencies.get("transport"),
            max_completion_tokens=model.get("max_completion_tokens", 32),
            max_repair_attempts=model.get("max_repair_attempts", 1),
        )
    raise ConfigurationError(f"unknown generator kind: {kind}")


def create_backend(config: dict[str, Any], **dependencies: Any):
    backend = config.get("decision_backend", {})
    kind = backend.get("kind", "mock")
    common = {
        "base_url": backend.get("base_url"),
        "model": backend.get("model"),
        "timeout_seconds": backend.get("timeout_seconds", 30),
        "transport": dependencies.get("transport"),
    }
    if kind == "mock":
        results = dependencies.get("results")
        if results is None:
            raise ConfigurationError("mock backend requires scripted results")
        return MockDecisionBackend(results, capabilities=dependencies.get("capabilities"))
    if kind == "jev_cloud":
        return JevCloudBackend(
            api_key=dependencies.get("api_key"),
            **{key: value for key, value in common.items() if value is not None},
        )
    if kind == "djev_local":
        return DjevLocalBackend(
            **{key: value for key, value in common.items() if value is not None},
            label_validator=dependencies.get("label_validator"),
            supports_native_multimodal=backend.get("supports_native_multimodal", False),
        )
    if kind == "laya_local":
        return LayaLocalBackend(
            **{key: value for key, value in common.items() if value is not None},
        )
    if kind == "cross_encoder":
        scorer = dependencies.get("scorer")
        coverage = dependencies.get("coverage_estimator")
        if scorer is None or coverage is None:
            raise ConfigurationError(
                "cross_encoder requires scorer and independent coverage_estimator"
            )
        return CrossEncoderDecisionBackend(
            scorer,
            coverage,
            model_name=backend.get("model") or "configured-cross-encoder",
        )
    if kind == "native_dlm":
        runtime = dependencies.get("runtime")
        if runtime is None and backend.get("runtime_kind") == "llada_http":
            runtime = LladaHTTPNativeReadRuntime(
                base_url=backend.get("base_url", "http://127.0.0.1:8002"),
                timeout_seconds=backend.get("timeout_seconds", 600),
                transport=dependencies.get("transport"),
                batch_reads=backend.get("batch_reads", False),
            )
        if runtime is None:
            raise ConfigurationError(
                "native_dlm requires an injected read runtime or runtime_kind: llada_http"
            )
        return NativeDLMDecisionBackend(
            runtime,
            label_validator=dependencies.get("label_validator"),
            runtime_name=backend.get("model") or "native-dlm",
        )
    raise ConfigurationError(f"unknown decision backend kind: {kind}")
