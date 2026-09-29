import math

import httpx
import pytest

from dicojev.backends import (
    LladaHTTPNativeReadRuntime,
    NativeDLMDecisionBackend,
    build_native_read_request,
)
from dicojev.config import create_backend
from dicojev.errors import BackendUnavailable, ConfigurationError
from dicojev.schemas import Candidate, DecisionSpec, MultimodalState


def fixture_spec():
    return DecisionSpec(
        task="Choose safely",
        candidates=(),
        selection_instruction="Choose the safest action",
        coverage_instruction="Is an acceptable action available?",
    )


def fixture_candidates():
    return [
        Candidate(id="A", action="Review recipients"),
        Candidate(id="N", action="None of the above", synthetic=True),
    ]


def test_native_read_canvas_is_deterministic_and_separates_questions():
    state = MultimodalState(text="Draft ready", structured={"verified": False})
    coverage = build_native_read_request("coverage", state, fixture_spec(), fixture_candidates())
    selection = build_native_read_request("selection", state, fixture_spec(), fixture_candidates())

    assert coverage.labels == ("0", "1")
    assert selection.labels == ("A", "N")
    assert '"verified":false' in coverage.prompt
    assert '"action":"Review recipients","label":"A"' in coverage.prompt
    assert coverage.prompt != selection.prompt
    assert coverage.state is state


@pytest.mark.asyncio
async def test_native_backend_normalizes_binary_and_categorical_logits():
    class Runtime:
        def __init__(self):
            self.requests = []

        def read(self, request):
            self.requests.append(request)
            return [-2.0, 2.0] if request.mode == "coverage" else [3.0, 1.0]

    runtime = Runtime()
    backend = NativeDLMDecisionBackend(runtime, runtime_name="fixture-dlm")
    result = await backend.decide(
        MultimodalState(text="Draft ready"), fixture_spec(), fixture_candidates()
    )

    assert result.backend == "native_dlm"
    assert result.coverage.raw == pytest.approx(1 / (1 + math.exp(-4)))
    assert result.selection.selected_id == "A"
    assert sum(result.selection.probabilities.values()) == pytest.approx(1.0)
    assert [request.mode for request in runtime.requests] == ["coverage", "selection"]
    assert result.diagnostics["runtime"] == "fixture-dlm"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidates",
    [
        [],
        [Candidate(id="AA", action="Invalid multi-token label")],
        [Candidate(id="A", action="One"), Candidate(id="A", action="Duplicate")],
    ],
)
async def test_native_backend_rejects_unsafe_labels_before_read(candidates):
    class Runtime:
        def read(self, _request):
            raise AssertionError("runtime must not be called")

    with pytest.raises(BackendUnavailable):
        await NativeDLMDecisionBackend(Runtime()).decide(
            MultimodalState(text="x"), fixture_spec(), candidates
        )


@pytest.mark.asyncio
async def test_native_backend_rejects_wrong_logit_count():
    class Runtime:
        def read(self, _request):
            return [0.0]

    with pytest.raises(BackendUnavailable, match="coverage.*1 logits.*2 labels"):
        await NativeDLMDecisionBackend(Runtime()).decide(
            MultimodalState(text="x"), fixture_spec(), fixture_candidates()
        )


def test_native_backend_configuration_requires_runtime():
    with pytest.raises(ConfigurationError, match="injected read runtime"):
        create_backend({"decision_backend": {"kind": "native_dlm"}})

    runtime = object()
    backend = create_backend(
        {"decision_backend": {"kind": "native_dlm", "model": "fixture"}}, runtime=runtime
    )
    assert isinstance(backend, NativeDLMDecisionBackend)
    assert backend.runtime is runtime

    configured = create_backend(
        {
            "decision_backend": {
                "kind": "native_dlm",
                "runtime_kind": "llada_http",
                "base_url": "http://llada",
            }
        }
    )
    assert isinstance(configured.runtime, LladaHTTPNativeReadRuntime)
    assert configured.runtime.base_url == "http://llada"


@pytest.mark.asyncio
async def test_llada_http_runtime_transports_native_read_canvas():
    captured = {}

    def handler(request):
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={"logits": [-1.0, 1.0], "diagnostics": {"vision_cache_hit": False}},
        )

    runtime = LladaHTTPNativeReadRuntime(transport=httpx.MockTransport(handler))
    read = build_native_read_request(
        "coverage", MultimodalState(text="x"), fixture_spec(), fixture_candidates()
    )
    assert await runtime.read(read) == [-1.0, 1.0]
    assert captured["labels"] == ["0", "1"]
    assert captured["prompt"] == read.prompt
    assert captured["images"] == []
    assert runtime.diagnostics["coverage"] == {"vision_cache_hit": False}
