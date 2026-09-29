import base64
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from dicojev.backends import DjevLocalBackend
from dicojev.generator import DiffusionGemmaGenerator
from dicojev.multimodal import materialize_image
from dicojev.schemas import Candidate, DecisionRequest, DecisionSpec, ImageRef, MultimodalState

PNG = b"\x89PNG\r\n\x1a\nfixture"


def request_with(image: ImageRef) -> DecisionRequest:
    return DecisionRequest(state=MultimodalState(text="Inspect", images=(image,)), goal="Choose")


def spec() -> DecisionSpec:
    return DecisionSpec(
        task="Choose",
        candidates=(Candidate(id="A", action="Inspect image"),),
        selection_instruction="Choose",
        coverage_instruction="Covered?",
    )


def test_image_ref_requires_one_typed_source_and_bounds_bytes():
    with pytest.raises(ValidationError, match="exactly one"):
        ImageRef()
    with pytest.raises(ValidationError, match="exactly one"):
        ImageRef(uri="https://example.test/a.png", data=PNG, media_type="image/png")
    with pytest.raises(ValidationError, match="10 MiB"):
        ImageRef(data=b"x" * (10 * 1024 * 1024 + 1), media_type="image/png")


def test_generator_builds_native_multimodal_message_without_text_substitution():
    image = ImageRef(data=PNG, media_type="image/png", alt_text="fixture")
    messages = DiffusionGemmaGenerator().build_messages(request_with(image))
    content = messages[1]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1]) == PNG


def test_local_image_path_is_validated_and_materialized(tmp_path: Path):
    path = tmp_path / "fixture.png"
    path.write_bytes(PNG)
    native = materialize_image(ImageRef(uri=str(path)))
    assert native.media_type == "image/png"
    assert native.size_bytes == len(PNG)


@pytest.mark.asyncio
async def test_capable_djev_adapter_transports_native_image():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "result": {
                    "answers": {
                        "coverage": {"type": "noul", "noul": 0.9},
                        "selection": {
                            "type": "choice",
                            "choice": "A",
                            "probabilities": {"A": 1.0},
                            "confidence": 1.0,
                        },
                    }
                }
            },
        )

    backend = DjevLocalBackend(
        transport=httpx.MockTransport(handler), supports_native_multimodal=True
    )
    image = ImageRef(uri="data:image/png;base64," + base64.b64encode(PNG).decode("ascii"))
    await backend.decide(request_with(image).state, spec(), [Candidate(id="A", action="Inspect")])
    assert captured["state"]["images"][0]["url"].startswith("data:image/png;base64,")
    assert backend.capabilities.supports_native_multimodal
