import base64
import importlib.util
import json
import threading
import urllib.error
import urllib.request
from collections import OrderedDict
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace


def load_script(name: str):
    path = Path(__file__).parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_llada_message_flattening_supports_native_image_data_urls(monkeypatch):
    module = load_script("llada_openai_server.py")
    png = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xcf"
        b"\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND"
        b"\xaeB`\x82"
    ).decode()
    monkeypatch.setattr(module, "decode_image_url", lambda _url: SimpleNamespace(size=(1, 1)))
    prompt, images = module.flatten_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{png}"},
                    },
                ],
            }
        ]
    )
    assert "user: Describe <image>" in prompt
    assert images[0].size == (1, 1)


def test_runtime_probe_reports_unavailable_without_raising():
    module = load_script("runtime_matrix.py")
    result = module.probe("http://127.0.0.1:9/health", timeout=0.01)
    assert result["available"] is False


def test_llada_http_contract_reports_real_usage_and_validates_requests():
    module = load_script("llada_openai_server.py")

    class Runtime:
        def complete(self, messages, max_tokens, steps, temperature):
            assert messages == [{"role": "user", "content": "hello"}]
            assert (max_tokens, steps) == (8, 2)
            assert temperature == 0.2
            return "world", 3, 1

        def structured_read(self, prompt, labels, images):
            assert prompt == "choose"
            assert labels == ["A", "N"]
            assert images == []
            return [2.0, -1.0], [32, 45], 7, True

        def structured_read_batch(self, reads, images):
            assert [read["labels"] for read in reads] == [["0", "1"], ["A", "N"]]
            assert images == []
            return (
                [
                    {"logits": [-1.0, 1.0], "label_token_ids": [15, 16], "prompt_tokens": 8},
                    {"logits": [2.0, -2.0], "label_token_ids": [32, 45], "prompt_tokens": 9},
                ],
                False,
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), module.make_handler(Runtime(), "fixture"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        body = json.dumps(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 8,
                "steps": 2,
            }
        ).encode()
        request = urllib.request.Request(
            base_url + "/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            payload = json.load(response)
        assert payload["choices"][0]["message"]["content"] == "world"
        assert payload["usage"] == {
            "prompt_tokens": 3,
            "completion_tokens": 1,
            "total_tokens": 4,
        }

        invalid = urllib.request.Request(
            base_url + "/v1/chat/completions",
            data=json.dumps({"messages": [], "max_tokens": 1}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(invalid)
        except urllib.error.HTTPError as error:
            assert error.code == 422
        else:
            raise AssertionError("invalid request should return HTTP 422")

        native = urllib.request.Request(
            base_url + "/v1/structured-read",
            data=json.dumps({"prompt": "choose", "labels": ["A", "N"]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(native) as response:
            native_payload = json.load(response)
        assert native_payload["logits"] == [2.0, -1.0]
        assert native_payload["label_token_ids"] == [32, 45]
        assert native_payload["usage"] == {"prompt_tokens": 7}
        assert native_payload["diagnostics"]["vision_cache_hit"] is True

        batch = urllib.request.Request(
            base_url + "/v1/structured-read-batch",
            data=json.dumps(
                {
                    "reads": [
                        {"prompt": "covered?", "labels": ["0", "1"]},
                        {"prompt": "choose", "labels": ["A", "N"]},
                    ]
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(batch) as response:
            batch_payload = json.load(response)
        assert [result["logits"] for result in batch_payload["results"]] == [
            [-1.0, 1.0],
            [2.0, -2.0],
        ]
        assert batch_payload["diagnostics"]["batch_size"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_llada_json_normalization_drops_provider_candidate_ids():
    module = load_script("llada_openai_server.py")
    content = module.normalize_json_object(
        '{"candidates":[{"id":"B","action":"verify","tool":"mail"}]}'
    )
    assert json.loads(content) == {"candidates": [{"action": "verify", "tool": "mail"}]}


def test_llada_vision_features_are_lru_cached_by_image_content():
    module = load_script("llada_openai_server.py")
    calls = []

    class Image:
        mode = "RGB"
        size = (1, 1)

        def tobytes(self):
            return b"pixel"

    class Tensor:
        ndim = 4

    class Model:
        def encode_images(self, tensors):
            calls.append(tensors)
            return object()

    runtime = object.__new__(module.LladaRuntime)
    runtime.model = Model()
    runtime.torch = SimpleNamespace(cat=lambda tensors, dim: (tuple(tensors), dim))
    runtime.vision_cache_entries = 1
    runtime.vision_feature_cache = OrderedDict()

    first, first_hit = runtime._image_features([Image()], [Tensor()])
    second, second_hit = runtime._image_features([Image()], [Tensor()])

    assert first is second
    assert first_hit is False
    assert second_hit is True
    assert len(calls) == 1
