import json

import httpx
import pytest

from dicojev.intent import DLMIntentInferer
from dicojev.model_discovery import (
    discover_local_model,
    validate_cloud_model,
    validate_model_role,
    validate_model_standard,
)


def test_local_discovery_requires_weights_and_checks_role(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"model_type": "llada"}))
    with pytest.raises(ValueError, match="No supported model"):
        discover_local_model(str(tmp_path), "language")
    (tmp_path / "weights.safetensors").write_bytes(b"fixture")
    assert discover_local_model(str(tmp_path), "language")["adapter"] == "llada"
    assert discover_local_model(str(tmp_path), "decision")["adapter"] == "native_dlm"


def test_decision_descriptor_discovery(tmp_path):
    (tmp_path / "dicojev-model.json").write_text(
        json.dumps(
            {
                "role": "decision",
                "adapter": "laya_local",
                "endpoint": "http://127.0.0.1:8000",
                "model_identifier": "english",
            }
        )
    )
    (tmp_path / "weights.bin").write_bytes(b"fixture")
    assert discover_local_model(str(tmp_path), "decision")["model_identifier"] == "english"
    with pytest.raises(ValueError, match="not a language model"):
        validate_model_role("laya_local", "language")


def test_adapter_standards_separate_role_and_deployment():
    validate_model_standard("llada", "language", "local")
    validate_model_standard("native_dlm", "decision", "local")
    validate_model_standard("mercury", "language", "online")
    validate_model_standard("jev_cloud", "decision", "online")
    with pytest.raises(ValueError, match="not supported"):
        validate_model_standard("mercury", "language", "local")
    with pytest.raises(ValueError, match="not supported"):
        validate_model_standard("laya_local", "decision", "online")


@pytest.mark.asyncio
async def test_partial_intent_preserves_fields_and_generates_options():
    def handler(request):
        prompt = json.loads(request.content)["messages"][1]["content"]
        assert "do not force" in prompt
        assert "Supplied fields" in prompt
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "goal": "Replacement",
                                    "instruction": "Compare plans",
                                    "constraints": [],
                                    "suggested_tools": [],
                                    "options": ["Plan A", "Plan B"],
                                    "confidence": 0.8,
                                }
                            )
                        }
                    }
                ]
            },
        )

    draft = await DLMIntentInferer(
        base_url="http://test", model="m", transport=httpx.MockTransport(handler)
    ).infer(
        "Two plans",
        partial_fields={"goal": "My goal", "constraints": ["Budget 50"]},
    )
    assert draft.goal == "My goal"
    assert draft.constraints == ("Budget 50",)
    assert draft.options == ("Plan A", "Plan B")


@pytest.mark.asyncio
async def test_mercury_intent_reserves_tokens_for_visible_json():
    def handler(request):
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 1000
        assert payload["reasoning_effort"] == "low"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "goal": "Clarify the user's 2D game question",
                                    "instruction": "Ask what they want to know.",
                                    "constraints": [],
                                    "suggested_tools": [],
                                    "options": [],
                                    "assumptions": [],
                                    "confidence": 0.5,
                                    "needs_clarification": True,
                                    "clarifying_question": "What would you like to know?",
                                }
                            )
                        }
                    }
                ]
            },
        )

    draft = await DLMIntentInferer(
        base_url="http://test", model="mercury-2.5", transport=httpx.MockTransport(handler)
    ).infer("2D video games")
    assert draft.needs_clarification is True


@pytest.mark.asyncio
async def test_attachment_intent_does_not_expose_internal_vision_as_user_tool():
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "goal": "Describe the attached picture",
                                    "instruction": "Identify visible subjects.",
                                    "constraints": [],
                                    "suggested_tools": ["vision_model", "image_analysis_tool"],
                                    "options": [],
                                    "assumptions": [],
                                    "confidence": 0.8,
                                    "needs_clarification": False,
                                    "clarifying_question": None,
                                }
                            )
                        }
                    }
                ]
            },
        )

    draft = await DLMIntentInferer(
        base_url="http://test", model="fixture", transport=httpx.MockTransport(handler)
    ).infer(
        "What is the picture about?",
        partial_fields={"attachments": [{"name": "picture.png", "kind": ".png"}]},
    )

    assert draft.suggested_tools == ()


@pytest.mark.asyncio
async def test_cloud_model_type_validation():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
    )
    await validate_cloud_model("https://test/v1", "fixture", "m", "language", transport=transport)
    with pytest.raises(ValueError, match="not a decision model"):
        await validate_cloud_model("https://test", "fixture", "m", "decision", transport=transport)
    with pytest.raises(ValueError, match="API key"):
        await validate_cloud_model("https://test", "", "m", "language", transport=transport)
