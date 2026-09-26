import json

import httpx
import pytest

from dicojev.backends import (
    CrossEncoderDecisionBackend,
    DjevLocalBackend,
    JevCloudBackend,
    LayaLocalBackend,
    compile_systemone_request,
)
from dicojev.config import create_backend, create_generator
from dicojev.errors import ConfigurationError, MalformedProviderResponse
from dicojev.schemas import Candidate, DecisionSpec, MultimodalState


def spec():
    return DecisionSpec(
        task="Choose",
        candidates=(),
        selection_instruction="Select safest",
        coverage_instruction="Is any acceptable?",
    )


def candidates():
    return [Candidate(id="A", action="Review"), Candidate(id="N", action="None", synthetic=True)]


def response():
    return {
        "model": "fixture",
        "answers": {
            "coverage": {"type": "noul", "noul": 0.8},
            "selection": {
                "type": "choice",
                "choice": "A",
                "probabilities": {"A": 0.9, "N": 0.1},
                "confidence": 0.9,
            },
        },
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "elapsedMs": 12,
        "diagnostics": {"diffusion_steps": 16},
    }


def test_official_systemone_wire_shape():
    payload = compile_systemone_request(
        MultimodalState(text="draft"), spec(), candidates(), model="jev-latest"
    )
    assert payload["questions"]["coverage"]["type"] == "noul"
    assert payload["questions"]["selection"]["criteria"] == {
        "A": "Review",
        "N": "None",
    }
    assert "jev" not in payload["state"]


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_kind", ["jev", "djev", "laya"])
async def test_same_candidate_set_reaches_systemone_backends(backend_kind):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=response())

    transport = httpx.MockTransport(handler)
    if backend_kind == "jev":
        backend = JevCloudBackend(api_key="fixture", transport=transport)
    elif backend_kind == "djev":
        backend = DjevLocalBackend(transport=transport)
    else:
        backend = LayaLocalBackend(transport=transport)
    result = await backend.decide(MultimodalState(text="draft"), spec(), candidates())
    assert result.coverage.raw == 0.8
    assert result.selection.selected_id == "A"
    assert result.coverage.calibrated is None
    assert result.diagnostics["provider_elapsed_ms"] == 12
    assert result.diagnostics["provider_diagnostics"] == {"diffusion_steps": 16}
    assert seen[0]["questions"]["selection"]["criteria"]["A"] == "Review"


def test_jev_credentials_are_environment_only(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        JevCloudBackend()


def test_jev_uses_official_typesafe_endpoint_by_default():
    backend = JevCloudBackend(api_key="fixture")
    assert backend.base_url == "https://api.typesafe.ai"


@pytest.mark.asyncio
async def test_malformed_provider_response_is_rejected():
    backend = DjevLocalBackend(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"answers": {}}))
    )
    with pytest.raises(MalformedProviderResponse):
        await backend.decide(MultimodalState(text="x"), spec(), candidates())


@pytest.mark.asyncio
async def test_systemone_adapter_normalizes_bounded_provider_rounding():
    rounded = response()
    rounded["answers"]["selection"].update(
        {
            "choice": "A",
            "probabilities": {"A": 0.3333, "B": 0.3333, "N": 0.3333},
            "confidence": 0.3333,
        }
    )
    backend = LayaLocalBackend(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=rounded))
    )
    expanded_candidates = [
        Candidate(id="A", action="Review"),
        Candidate(id="B", action="Wait"),
        Candidate(id="N", action="None", synthetic=True),
    ]
    result = await backend.decide(MultimodalState(text="x"), spec(), expanded_candidates)
    assert sum(result.selection.probabilities.values()) == pytest.approx(1.0)
    assert result.diagnostics["selection_probability_sum_raw"] == pytest.approx(0.9999)


@pytest.mark.asyncio
async def test_cross_encoder_keeps_coverage_separate_from_selection():
    async def scorer(_state, _spec, _candidates):
        return [8.0, 1.0]

    async def coverage(_state, _spec, _candidates):
        return 0.2, "fixture_set_adequacy"

    backend = CrossEncoderDecisionBackend(scorer, coverage, model_name="fixture-ranker")
    semantic = [Candidate(id="A", action="Review"), Candidate(id="B", action="Send")]
    result = await backend.decide(MultimodalState(text="draft"), spec(), semantic)
    assert result.selection.confidence_raw > 0.99
    assert result.coverage.raw == 0.2
    assert result.coverage.method == "fixture_set_adequacy"


def test_config_only_component_selection():
    generator = create_generator(
        {"model": {"generator_kind": "diffusiongemma", "base_url": "http://model"}}
    )
    assert generator.base_url == "http://model"
    backend = create_backend(
        {"decision_backend": {"kind": "djev_local", "base_url": "http://djev"}}
    )
    assert isinstance(backend, DjevLocalBackend)
    backend = create_backend(
        {"decision_backend": {"kind": "laya_local", "base_url": "http://laya"}}
    )
    assert isinstance(backend, LayaLocalBackend)
    with pytest.raises(ConfigurationError):
        create_backend({"decision_backend": {"kind": "unknown"}})
