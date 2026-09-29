import base64
import importlib.util
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
