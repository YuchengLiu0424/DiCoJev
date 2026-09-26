"""Configuration loading and component factories."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .backends import DjevLocalBackend, JevCloudBackend, LayaLocalBackend, MockDecisionBackend
from .backends.cross_encoder import CrossEncoderDecisionBackend
from .errors import ConfigurationError
from .generator import DiffusionGemmaGenerator, FakeCandidateGenerator


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
        return MockDecisionBackend(results)
    if kind == "jev_cloud":
        return JevCloudBackend(
            api_key=dependencies.get("api_key"),
            **{key: value for key, value in common.items() if value is not None},
        )
    if kind == "djev_local":
        return DjevLocalBackend(
            **{key: value for key, value in common.items() if value is not None},
            label_validator=dependencies.get("label_validator"),
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
    raise ConfigurationError(f"unknown decision backend kind: {kind}")
