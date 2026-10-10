import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from dicojev.agent import ProjectAgentTools
from dicojev.direct import DirectClient
from dicojev.gui import build_parser, build_request, present_response, split_items
from dicojev.intent import DLMIntentInferer, fallback_intent_draft
from dicojev.memory import LocalMemoryStore
from dicojev.multimedia import LocalMediaIngestor, LocalVisionBridge
from dicojev.routing import route_direct_answer
from dicojev.schemas import (
    ControllerDecision,
    DecisionBackendResult,
    DecisionRequest,
    DecisionResponse,
    FeedbackBundle,
    FeedbackCode,
    FeedbackSignal,
    ImageRef,
    MetaAction,
    MultimodalState,
)
from dicojev.secrets import SecretStore
from dicojev.workspace import ProjectWorkspace


class EchoRuntime:
    async def decide(self, request):
        return request


def test_direct_client_calls_runtime_without_api_transport():
    request = DecisionRequest(state=MultimodalState(text="state"), goal="choose")
    client = DirectClient(EchoRuntime())
    assert client.decide_sync(request) is request
    assert asyncio.run(client.decide(request)) is request


def test_direct_client_aggregates_reported_generator_and_read_tokens():
    generator = SimpleNamespace(
        diagnostics={
            "generation_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
            },
            "reads": {
                "coverage": {"usage": {"input_tokens": 6, "output_tokens": 1}},
                "selection": {"usage": {"input_tokens": 7, "output_tokens": 1}},
            },
        }
    )
    runtime = SimpleNamespace(orchestrator=SimpleNamespace(generator=generator))
    usage = DirectClient(runtime).usage_snapshot()
    assert usage == {"prompt_tokens": 23, "completion_tokens": 6, "total_tokens": 29}


@pytest.mark.asyncio
async def test_direct_sync_call_rejects_active_event_loop():
    request = DecisionRequest(state=MultimodalState(), goal="choose")
    with pytest.raises(RuntimeError, match="active event loop"):
        DirectClient(EchoRuntime()).decide_sync(request)


def test_gui_request_builder_parses_simple_fields():
    request = build_request(
        context="Customer reports two charges",
        goal="Choose the safest action",
        tools="inspect, refund\nescalate",
        constraints="verify first\nno duplicate refund",
        structured_json='{"verified": true}',
    )
    assert request.available_tools == ("inspect", "refund", "escalate")
    assert request.constraints == ("verify first", "no duplicate refund")
    assert request.state.structured == {"verified": True}
    assert split_items(" a, b\nc ") == ("a", "b", "c")


def test_native_gui_uses_packaged_config_by_default():
    args = build_parser().parse_args([])
    assert Path(args.config).name == "default.yaml"
    assert args.account == "default"
    assert args.data_dir is None


@pytest.mark.asyncio
async def test_context_only_intent_is_structured_for_user_review():
    async def handler(request):
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"goal":"Choose a safe response","instruction":"Compare responses",'
                                '"constraints":["Protect private data"],"suggested_tools":["lookup_account"],'
                                '"assumptions":[],"confidence":0.86,"needs_clarification":false,'
                                '"clarifying_question":null}'
                            )
                        }
                    }
                ]
            },
        )

    inferer = DLMIntentInferer(
        base_url="http://local.test",
        model="local-dlm",
        transport=httpx.MockTransport(handler),
    )
    draft = await inferer.infer("A long, unstructured customer description")
    assert draft.goal == "Choose a safe response"
    assert draft.suggested_tools == ("lookup_account",)
    assert draft.confidence == 0.86


def test_context_only_offline_fallback_is_explicit_and_review_only():
    draft = fallback_intent_draft(
        "The customer wrote a long explanation but did not specify the exact action."
    )
    assert draft.goal.startswith("Clarify the requested outcome")
    assert draft.confidence == 0.25
    assert draft.needs_clarification is True
    assert "DLM was unavailable" in draft.assumptions[0]


def test_unambiguous_arithmetic_routes_to_safe_direct_answer():
    answer = route_direct_answer("calculate 1+3")
    assert answer is not None
    assert answer.answer == "4"
    assert answer.confidence == 1.0
    assert route_direct_answer("calculate 1/0") is None
    assert route_direct_answer("calculate __import__('os').system('whoami')") is None
    assert route_direct_answer("I have 1+3 apples") is None


def test_component_failure_is_presented_as_unavailable_not_epistemic_escalation():
    reason = "component_failure:GeneratorUnavailable"
    feedback = FeedbackBundle(
        primary=FeedbackSignal(code=FeedbackCode.INSUFFICIENT_INFORMATION),
        source_round=0,
        controller_reason_code=reason,
        generation_relevant=False,
    )
    response = DecisionResponse(
        action=MetaAction.ESCALATE,
        candidates=(),
        controller=ControllerDecision(
            action=MetaAction.ESCALATE,
            reason_code=reason,
            feedback=feedback,
        ),
        backend_result=DecisionBackendResult(
            backend="unavailable", diagnostics={"error_type": "GeneratorUnavailable"}
        ),
        feedback=feedback,
        trace=(),
    )
    presentation = present_response(response)
    assert presentation.action == "UNAVAILABLE"
    assert presentation.feedback == "SERVICE · GeneratorUnavailable"
    assert "model service" in presentation.selected


def test_local_memory_separates_chats_and_bounds_history(tmp_path):
    store = LocalMemoryStore(tmp_path / "profile")
    first = store.create_chat("local", "First")
    second = store.create_chat("local", "Second")
    store.append_turn(first, "user", {"goal": "A", "summary": "first user"})
    store.append_turn(first, "assistant", {"summary": "first answer"})
    store.append_turn(second, "user", {"goal": "B", "summary": "second user"})

    assert len(store.list_chats("local")) == 2
    assert store.decision_history(first, limit=1) == ("assistant: first answer",)
    assert store.decision_history(second) == ("user: second user",)
    assert store.latest_turn(first, "user")["goal"] == "A"


def test_projects_own_chats_and_model_assignments_persist(tmp_path):
    store = LocalMemoryStore(tmp_path)
    unassigned = store.create_chat("local")
    first = store.create_project("local", "First")
    second = store.create_project("local", "Second")
    chat = store.create_chat("local", project_id=first)
    other = store.create_chat("local", project_id=second)
    assert [item.id for item in store.list_chats("local", first)] == [chat]
    assert [item.id for item in store.list_chats("local", second)] == [other]
    assert [item.id for item in store.list_unassigned_chats("local")] == [unassigned]
    defaults = store.get_chat_models(chat)
    models = {item.id: item for item in store.list_models("local")}
    assert models[defaults.language_model_id].name == "LLaDA Local"
    assert models[defaults.language_model_id].adapter == "llada"
    assert models[defaults.decision_model_id].adapter == "native_dlm"
    added = store.add_model(
        "local",
        name="My LLM",
        role="language",
        deployment="local",
        adapter="openai_compatible",
        location="http://127.0.0.1:9000",
        model_identifier="my-model",
    )
    store.set_chat_models(chat, added, defaults.decision_model_id)
    assert store.get_chat_models(other).language_model_id != added
    store.set_chat_project(other, None)
    assert {item.id for item in store.list_unassigned_chats("local")} == {unassigned, other}
    store.set_chat_project(other, second)
    reopened = LocalMemoryStore(tmp_path)
    assert reopened.get_chat_models(chat).language_model_id == added
    assert (
        next(item for item in reopened.list_models("local") if item.id == added).model_identifier
        == "my-model"
    )
    with pytest.raises(ValueError, match="role"):
        store.set_chat_models(chat, defaults.decision_model_id, defaults.language_model_id)
    store.rename_project(first, "Renamed")
    store.delete_project(first)
    assert not store.list_turns(chat)
    assert {item.id for item in store.list_chats("local")} == {unassigned, other}


def test_separate_model_runtime_uses_explicit_keys_without_environment(monkeypatch):
    monkeypatch.setenv("MERCURY_API_KEY", "unwanted-environment-key")
    monkeypatch.setenv("JEV_API_KEY", "unwanted-environment-key")
    config = {
        "model": {
            "deployment": "separate_models",
            "generator_kind": "mercury",
            "generator_model": "mercury-2.5",
            "base_url": "https://language.test/v1",
        },
        "decision_backend": {
            "kind": "jev_cloud",
            "model": "jev-latest",
            "base_url": "https://decision.test",
        },
    }
    client = DirectClient.from_config(
        config,
        generator_api_key="language-key",
        decision_api_key="decision-key",
        use_environment=False,
    )
    assert client.runtime.orchestrator.generator.api_key == "language-key"
    assert client.runtime.orchestrator.backend.api_key == "decision-key"
    empty = DirectClient.from_config(config, use_environment=False)
    assert empty.runtime.orchestrator.generator.api_key is None
    assert empty.runtime.orchestrator.backend.api_key is None


@pytest.mark.asyncio
async def test_local_diffusiongemma_and_laya_execute_as_separate_models():
    calls = []

    def handler(request):
        calls.append((request.url.host, request.url.port, request.url.path))
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": '{"candidates":[{"action":"Inspect the report"}]}'}}
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 5},
                },
            )
        return httpx.Response(
            200,
            json={
                "result": {
                    "answers": {
                        "coverage": {"type": "noul", "noul": 0.95},
                        "selection": {
                            "type": "choice",
                            "choice": "A",
                            "confidence": 0.9,
                            "probabilities": {"A": 0.9, "N": 0.1},
                        },
                    },
                    "usage": {"prompt_tokens": 8, "completion_tokens": 1},
                }
            },
        )

    client = DirectClient.from_config(
        {
            "model": {
                "deployment": "separate_models",
                "generator_kind": "diffusiongemma",
                "base_url": "http://127.0.0.1:11434",
                "generator_model": "dicojev-diffusiongemma",
            },
            "decision_backend": {
                "kind": "laya_local",
                "base_url": "http://127.0.0.1:8000",
                "model": "english",
            },
        },
        transport=httpx.MockTransport(handler),
    )
    response = await client.decide(
        DecisionRequest(
            state=MultimodalState(text="A report arrived"), goal="Choose the next action"
        )
    )
    assert response.action == MetaAction.ACT
    assert calls == [
        ("127.0.0.1", 11434, "/v1/chat/completions"),
        ("127.0.0.1", 8000, "/v1/systemone"),
    ]


def test_local_memory_reserves_explicit_long_term_memory_table(tmp_path):
    store = LocalMemoryStore(tmp_path / "profile")
    chat = store.create_chat("local")
    store.remember("local", "User prefers conservative actions", chat_id=chat, salience=0.9)
    with store._connect() as connection:
        row = connection.execute("SELECT content, salience FROM memories").fetchone()
    assert tuple(row) == ("User prefers conservative actions", 0.9)


def test_chat_management_defaults_renames_deletes_and_lists_turns(tmp_path):
    store = LocalMemoryStore(tmp_path / "profile")
    first = store.create_chat("local")
    second = store.create_chat("local")
    assert [chat.title for chat in store.list_chats("local")] == ["Chat 2", "Chat 1"]
    store.rename_chat(first, "Important decision")
    store.append_turn(first, "user", {"summary": "Question"})
    assert store.list_turns(first)[0].content["summary"] == "Question"
    store.delete_chat(second)
    assert [chat.title for chat in store.list_chats("local")] == ["Important decision"]


def test_usage_is_aggregated_by_model_and_chat(tmp_path):
    store = LocalMemoryStore(tmp_path / "profile")
    chat = store.create_chat("local")
    store.record_usage(
        "local",
        chat,
        "mercury-2.5",
        "decision",
        {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
    )
    store.record_usage(
        "local", chat, "mercury-2.5", "intent", {"input_tokens": 3, "output_tokens": 2}
    )
    summary = store.usage_summary("local")[0]
    assert (summary.input_tokens, summary.output_tokens, summary.total_tokens, summary.calls) == (
        14,
        6,
        20,
        2,
    )


def test_secret_store_persists_only_protected_payload(tmp_path, monkeypatch):
    monkeypatch.setattr("dicojev.secrets._dpapi", lambda value, decrypt: value[::-1])
    store = SecretStore(tmp_path)
    store.set("model_api_key", "private-key")
    assert store.get("model_api_key") == "private-key"
    assert "private-key" not in store.path.read_text(encoding="utf-8")
    store.set("model_api_key", "")
    assert store.get("model_api_key") is None


def test_project_workspace_confines_file_access(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "note.txt").write_text("hello", encoding="utf-8")
    workspace = ProjectWorkspace(root)
    assert workspace.list_files() == ("note.txt",)
    assert workspace.read_text("note.txt") == "hello"
    with pytest.raises(ValueError, match="escapes"):
        workspace.read_text("../outside.txt")
    with pytest.raises(PermissionError, match="not granted"):
        workspace.write_text("new.txt", "content")


def test_project_agent_tools_are_allowlist_ready_and_write_gated(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "note.txt").write_text("hello", encoding="utf-8")
    state = MultimodalState()
    tools = ProjectAgentTools(ProjectWorkspace(root)).handlers()
    listing, unchanged = tools["list_project_files"](state, {})
    reading, _ = tools["read_project_file"](state, {"path": "note.txt"})
    assert listing == {"files": ["note.txt"]}
    assert reading["content"] == "hello"
    assert unchanged is state
    with pytest.raises(PermissionError, match="not granted"):
        tools["write_project_file"](state, {"path": "new.txt", "content": "x"})


def test_media_ingestor_adds_text_image_and_metadata(tmp_path):
    note = tmp_path / "note.txt"
    note.write_text("Account is verified.", encoding="utf-8")
    image = tmp_path / "screen.png"
    image.write_bytes(b"small-fixture")
    request = DecisionRequest(state=MultimodalState(text="Original state"), goal="decide")

    enriched = LocalMediaIngestor().enrich_request(request, [str(note), str(image)])

    assert "[File: note.txt]" in enriched.state.text
    assert "Account is verified." in enriched.state.text
    assert enriched.state.images[0].data == b"small-fixture"
    assert enriched.state.images[0].media_type == "image/png"
    assert enriched.state.structured["attachments"] == [
        {"name": "note.txt", "kind": "text", "size_bytes": 20},
        {"name": "screen.png", "kind": "image", "size_bytes": 13},
    ]


def test_media_ingestor_rejects_unknown_and_oversized_files(tmp_path):
    unknown = tmp_path / "payload.xyz"
    unknown.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported attachment type"):
        LocalMediaIngestor().ingest([str(unknown)])

    large = tmp_path / "large.txt"
    large.write_text("12345", encoding="utf-8")
    with pytest.raises(ValueError, match="Attachment exceeds"):
        LocalMediaIngestor(max_file_bytes=4).ingest([str(large)])


def test_local_vision_bridge_converts_images_to_provenanced_text():
    def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "qwen3.5:9b"
        assert payload["think"] is False
        assert len(payload["messages"][0]["images"]) == 1
        return httpx.Response(200, json={"message": {"content": "A blue dialog shows a warning."}})

    request = DecisionRequest(
        state=MultimodalState(
            text="What is shown?",
            images=(
                ImageRef(
                    data=b"\x89PNG\r\n\x1a\nfixture", media_type="image/png", alt_text="dialog"
                ),
            ),
            structured={"attachments": [{"name": "dialog.png", "kind": "image"}]},
        ),
        goal="Describe the image",
    )
    enriched = LocalVisionBridge(transport=httpx.MockTransport(handler)).enrich_request(request)

    assert "[Local vision analysis · qwen3.5:9b]" in enriched.state.text
    assert "blue dialog" in enriched.state.text
    assert enriched.state.images == ()
    assert enriched.state.structured["vision_bridge"] == {
        "model": "qwen3.5:9b",
        "image_count": 1,
        "mode": "local_image_to_text_for_text_only_pair",
    }


def test_audio_intake_uses_lazy_local_transcriber(tmp_path):
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"fixture")
    ingestor = LocalMediaIngestor()
    segment = SimpleNamespace(text=" choose the safe action ")
    ingestor._speech_runtime = SimpleNamespace(
        transcribe=lambda _path, vad_filter: ([segment], {"language": "en"})
    )

    result = ingestor.ingest([str(audio)])

    assert result.text_blocks == ("[Speech transcript: speech.wav]\nchoose the safe action",)
    assert result.metadata[0]["kind"] == "audio"


def test_video_intake_samples_frames_and_transcript_without_real_codec(tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fixture")

    class Capture:
        def isOpened(self):
            return True

        def get(self, key):
            return 3 if key == 1 else 1.0

        def set(self, _key, _value):
            return None

        def read(self):
            return True, object()

        def release(self):
            return None

    buffer = SimpleNamespace(tobytes=lambda: b"jpeg")
    fake_cv2 = SimpleNamespace(
        CAP_PROP_FRAME_COUNT=1,
        CAP_PROP_FPS=2,
        CAP_PROP_POS_FRAMES=3,
        VideoCapture=lambda _path: Capture(),
        imencode=lambda _extension, _frame: (True, buffer),
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    ingestor = LocalMediaIngestor(video_frames=2)
    monkeypatch.setattr(ingestor, "_transcribe", lambda _path: "spoken context")

    result = ingestor.ingest([str(video)])

    assert result.text_blocks == ("[Video transcript: clip.mp4]\nspoken context",)
    assert result.images == (
        ImageRef(data=b"jpeg", media_type="image/jpeg", alt_text="clip.mp4 frame 0"),
        ImageRef(data=b"jpeg", media_type="image/jpeg", alt_text="clip.mp4 frame 2"),
    )
    assert result.metadata[0]["sampled_frames"] == 2
    assert result.metadata[0]["duration_seconds"] == 3.0
