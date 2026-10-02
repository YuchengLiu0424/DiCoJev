import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from dicojev.direct import DirectClient
from dicojev.gui import build_parser, build_request, split_items
from dicojev.intent import DLMIntentInferer
from dicojev.memory import LocalMemoryStore
from dicojev.multimedia import LocalMediaIngestor
from dicojev.schemas import DecisionRequest, ImageRef, MultimodalState


class EchoRuntime:
    async def decide(self, request):
        return request


def test_direct_client_calls_runtime_without_api_transport():
    request = DecisionRequest(state=MultimodalState(text="state"), goal="choose")
    client = DirectClient(EchoRuntime())
    assert client.decide_sync(request) is request
    assert asyncio.run(client.decide(request)) is request


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


def test_local_memory_reserves_explicit_long_term_memory_table(tmp_path):
    store = LocalMemoryStore(tmp_path / "profile")
    chat = store.create_chat("local")
    store.remember("local", "User prefers conservative actions", chat_id=chat, salience=0.9)
    with store._connect() as connection:
        row = connection.execute("SELECT content, salience FROM memories").fetchone()
    assert tuple(row) == ("User prefers conservative actions", 0.9)


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
