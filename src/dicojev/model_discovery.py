"""Conservative local model discovery; filenames alone do not establish capabilities."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from .backends.systemone import compile_systemone_request, normalize_systemone_response
from .errors import MalformedProviderResponse
from .schemas import Candidate, DecisionSpec, MultimodalState

ADAPTER_ROLES = {
    "diffusiongemma": "language",
    "llada": "language",
    "openai_compatible": "language",
    "mercury": "language",
    "laya_local": "decision",
    "djev_local": "decision",
    "jev_cloud": "decision",
    "native_dlm": "decision",
}

ADAPTER_STANDARDS = {
    ("language", "local"): ("llada", "diffusiongemma", "openai_compatible"),
    ("language", "online"): ("mercury", "openai_compatible"),
    ("decision", "local"): ("native_dlm", "laya_local", "djev_local"),
    ("decision", "online"): ("jev_cloud",),
}


async def validate_cloud_model(
    endpoint: str,
    key: str,
    model: str,
    role: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Probe protocol capability, not the spelling of a secret. May consume tokens."""
    if not key:
        raise ValueError("Enter an API key before validating a cloud model.")
    async with httpx.AsyncClient(
        timeout=30, transport=transport, headers={"Authorization": f"Bearer {key}"}
    ) as client:
        if role == "language":
            url = endpoint.rstrip("/")
            url += "/chat/completions" if url.endswith("/v1") else "/v1/chat/completions"
            response = await client.post(
                url,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply OK."}],
                    "max_tokens": 8,
                },
            )
        else:
            candidates = [
                Candidate(id="A", action="4"),
                Candidate(id="N", action="None", synthetic=True),
            ]
            spec = DecisionSpec(
                task="Calculate 1+3",
                candidates=tuple(candidates),
                selection_instruction="Choose the correct answer.",
                coverage_instruction="Is a correct answer present?",
            )
            response = await client.post(
                endpoint.rstrip("/") + "/v1/systemone",
                json=compile_systemone_request(
                    MultimodalState(text="1+3"),
                    spec,
                    candidates,
                    model=model,
                ),
            )
        if response.status_code in {401, 403}:
            raise ValueError("API key was rejected; model type could not be verified.")
        if response.status_code == 404:
            raise ValueError(
                f"This is not a {role} model endpoint, or the endpoint/model name is incorrect."
            )
        if not response.is_success:
            raise ValueError(
                f"Model service returned HTTP {response.status_code}; type is unverified."
            )
        try:
            payload = response.json()
            if role == "language":
                if not isinstance(payload["choices"][0]["message"]["content"], str):
                    raise ValueError("not text")
            else:
                normalize_systemone_response(payload, backend="registration_probe", latency_ms=0)
        except (ValueError, KeyError, IndexError, TypeError, MalformedProviderResponse) as error:
            raise ValueError(
                f"This is not a {role} model: incompatible service response."
            ) from error


def validate_model_role(adapter: str, role: str) -> None:
    if ADAPTER_ROLES.get(adapter) != role:
        raise ValueError(f"This is not a {role} model. Choose a matching model adapter.")


def validate_model_standard(adapter: str, role: str, deployment: str) -> None:
    """Require an adapter whose protocol matches both capability and transport."""
    validate_model_role(adapter, role)
    if adapter not in ADAPTER_STANDARDS.get((role, deployment), ()):
        raise ValueError(f"Adapter '{adapter}' is not supported for a {deployment} {role} model.")


def discover_local_model(folder: str, role: str) -> dict[str, str]:
    """Discover root or immediate-child HF models or explicit DiCoJev descriptors.

    A descriptor identifies decision-model capabilities that generic HF metadata cannot.
    Discovery never downloads weights, executes folder code, or starts a server.
    """
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Model folder does not exist.")
    candidates = [root, *sorted(p for p in root.iterdir() if p.is_dir())[:100]]
    found = []
    mismatched = False
    for candidate in candidates:
        descriptor = candidate / "dicojev-model.json"
        config = candidate / "config.json"
        if descriptor.is_file():
            data = json.loads(descriptor.read_text(encoding="utf-8"))
            adapter = data.get("adapter", "")
            detected_role = ADAPTER_ROLES.get(adapter)
            if data.get("role") != detected_role:
                raise ValueError("Model descriptor role and adapter disagree.")
        elif config.is_file():
            data = json.loads(config.read_text(encoding="utf-8"))
            architecture = " ".join(data.get("architectures", [])).lower()
            kind = str(data.get("model_type", "")).lower()
            if "llada" in kind + architecture:
                adapter = "native_dlm" if role == "decision" else "llada"
            elif "diffusiongemma" in kind + architecture:
                adapter = "diffusiongemma"
            elif "causallm" in architecture or "conditionalgeneration" in architecture:
                adapter = "openai_compatible"
            else:
                continue
            detected_role = "decision" if adapter == "native_dlm" else "language"
        else:
            continue
        if not any(
            p.is_file() and p.suffix in {".safetensors", ".bin", ".gguf", ".pt", ".pth"}
            for p in candidate.iterdir()
        ):
            continue
        if detected_role != role:
            mismatched = True
            continue
        found.append(
            {
                "path": str(candidate),
                "adapter": adapter,
                "model_identifier": str(data.get("model_identifier") or candidate.name),
                "endpoint": str(data.get("endpoint") or ""),
            }
        )
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        raise ValueError("Multiple models found. Select the specific model folder.")
    if mismatched:
        raise ValueError(f"This is not a {role} model.")
    raise ValueError(
        "No supported model with weights and verifiable type found. Select a model folder; "
        "decision models require a dicojev-model.json descriptor."
    )
