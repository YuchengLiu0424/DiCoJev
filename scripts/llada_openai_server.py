"""Serve the local LLaDA-V checkpoint through a small OpenAI-compatible API."""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def decode_image_url(url: str):
    from PIL import Image

    if url.startswith("data:"):
        _, encoded = url.split(",", 1)
        payload = base64.b64decode(encoded, validate=True)
    elif url.startswith(("http://", "https://")):
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read()
    else:
        payload = Path(url).read_bytes()
    return Image.open(io.BytesIO(payload)).convert("RGB")


def flatten_messages(messages: list[dict[str, Any]]) -> tuple[str, list[Any]]:
    lines: list[str] = []
    images: list[Any] = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = message.get("content", "")
        parts = [{"type": "text", "text": content}] if isinstance(content, str) else content
        text_parts: list[str] = []
        for part in parts or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                text_parts.append(str(part.get("text", "")))
            elif part.get("type") == "image_url":
                image_url = part.get("image_url", {})
                url = image_url.get("url") if isinstance(image_url, dict) else image_url
                if not isinstance(url, str):
                    raise ValueError("image_url must contain a string URL")
                images.append(decode_image_url(url))
                text_parts.append("<image>")
        lines.append(f"{role}: {' '.join(text_parts).strip()}")
    lines.append("assistant:")
    return "\n".join(lines), images


class LladaRuntime:
    def __init__(self, model_path: Path, code_path: Path) -> None:
        sys.path.insert(0, str(code_path / "train"))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")

        import torch
        from llava.constants import IMAGE_TOKEN_INDEX
        from llava.mm_utils import process_images, tokenizer_image_token
        from llava.model.language_model.llava_llada import LlavaLLaDAConfig, LlavaLLaDAModelLM
        from llava.model.multimodal_encoder.siglip_encoder import (
            SigLipVisionModel,
            SigLipVisionTower,
        )
        from transformers import AutoTokenizer

        def load_embedded_vision_model(tower, device_map=None):
            del device_map
            if tower.is_loaded:
                return
            tower.vision_tower = SigLipVisionModel(tower.config)
            del tower.vision_tower.vision_model.encoder.layers[-1:]
            tower.vision_tower.vision_model.head = torch.nn.Identity()
            tower.vision_tower.requires_grad_(False)
            tower.is_loaded = True

        SigLipVisionTower.load_model = load_embedded_vision_model
        config = LlavaLLaDAConfig.from_pretrained(model_path, local_files_only=True)
        self.model = LlavaLLaDAModelLM.from_pretrained(
            model_path,
            config=config,
            local_files_only=True,
            low_cpu_mem_usage=True,
            torch_dtype=torch.float16,
            attn_implementation="sdpa",
            device_map={"": "cpu"},
        ).eval()
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            use_fast=False,
            local_files_only=True,
            trust_remote_code=True,
        )
        self.torch = torch
        self.image_token_index = IMAGE_TOKEN_INDEX
        self.process_images = process_images
        self.tokenizer_image_token = tokenizer_image_token
        self.lock = threading.Lock()

    def complete(self, messages: list[dict[str, Any]], max_tokens: int, steps: int) -> str:
        prompt, images = flatten_messages(messages)
        if images:
            input_ids = self.tokenizer_image_token(
                prompt, self.tokenizer, self.image_token_index, return_tensors="pt"
            ).unsqueeze(0)
            vision_tower = self.model.get_vision_tower()
            image_tensors = self.process_images(
                images, vision_tower.image_processor, self.model.config
            )
            image_tensors = [
                tensor.to(dtype=self.torch.float16, device="cpu") for tensor in image_tensors
            ]
            image_sizes = [image.size for image in images]
        else:
            input_ids = self.tokenizer(prompt, return_tensors="pt").input_ids
            image_tensors = None
            image_sizes = None

        with self.lock:
            output = self.model.generate(
                input_ids,
                images=image_tensors,
                image_sizes=image_sizes,
                steps=steps,
                gen_length=max_tokens,
                block_length=max_tokens,
                tokenizer=self.tokenizer,
                stopping_criteria=["<|eot_id|>"],
            )
        return self.tokenizer.batch_decode(output, skip_special_tokens=True)[0].strip()


def make_handler(runtime: LladaRuntime, model_name: str):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_json(200, {"status": "ok", "model": model_name})
            elif self.path == "/v1/models":
                self.send_json(200, {"object": "list", "data": [{"id": model_name}]})
            else:
                self.send_json(404, {"error": {"message": "not found"}})

        def do_POST(self) -> None:
            if self.path != "/v1/chat/completions":
                self.send_json(404, {"error": {"message": "not found"}})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length))
                max_tokens = max(1, min(int(request.get("max_tokens", 64)), 256))
                steps = max(1, min(int(request.get("steps", max_tokens)), max_tokens))
                started = time.perf_counter()
                content = runtime.complete(request["messages"], max_tokens, steps)
                elapsed_ms = (time.perf_counter() - started) * 1000
                self.send_json(
                    200,
                    {
                        "id": f"chatcmpl-{time.time_ns()}",
                        "object": "chat.completion",
                        "model": model_name,
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": content},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 0,
                            "completion_tokens": max_tokens,
                            "total_tokens": max_tokens,
                        },
                        "diagnostics": {"elapsed_ms": elapsed_ms},
                    },
                )
            except Exception as error:  # noqa: BLE001  # pragma: no cover
                self.send_json(400, {"error": {"message": str(error)}})

        def log_message(self, format: str, *args: Any) -> None:
            print(format % args)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-path",
        type=Path,
        default=Path(os.getenv("LLADA_MODEL_PATH", r"D:\LLM\LLaDA-V")),
    )
    parser.add_argument(
        "--code-path",
        type=Path,
        default=Path(os.getenv("LLADA_CODE_PATH", r"D:\LLM\LLaDA-V-code")),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--model-name", default="llada-v-local")
    args = parser.parse_args()
    runtime = LladaRuntime(args.model_path, args.code_path)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime, args.model_name))
    print(f"LLaDA-V listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
