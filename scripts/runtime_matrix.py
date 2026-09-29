"""Report availability of supported DiCoJev runtimes without exposing secrets."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path
from typing import Any


def probe(url: str, timeout: float = 2.0) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {"available": response.status == 200, "status": response.status}
    except Exception as error:  # noqa: BLE001 - diagnostics must report every failure mode
        return {"available": False, "error": type(error).__name__}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--llada-path",
        type=Path,
        default=Path(os.getenv("LLADA_MODEL_PATH", r"D:\LLM\LLaDA-V")),
    )
    parser.add_argument(
        "--diffusiongemma-path",
        type=Path,
        default=Path(
            os.getenv(
                "DIFFUSIONGEMMA_MODEL_PATH",
                r"D:\LLM\diffusiongemma-26B-A4B-it-GGUF\diffusiongemma-26B-A4B-it-Q4_K_M.gguf",
            )
        ),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    llada_shards = sorted(args.llada_path.glob("model-*-of-*.safetensors"))
    report = {
        "mercury": {
            "configured": bool(os.getenv("MERCURY_API_KEY") or os.getenv("INCEPTION_API_KEY"))
        },
        "jev": {"configured": bool(os.getenv("JEV_API_KEY"))},
        "laya": probe(os.getenv("DICOJEV_LAYA_URL", "http://127.0.0.1:8000") + "/docs"),
        "djev": probe(os.getenv("DICOJEV_DJEV_URL", "http://127.0.0.1:8011") + "/health"),
        "llada": {
            **probe(os.getenv("DICOJEV_LLADA_URL", "http://127.0.0.1:8002") + "/health"),
            "weights_present": len(llada_shards) == 6,
            "shard_count": len(llada_shards),
        },
        "diffusiongemma": {
            **probe(os.getenv("DICOJEV_DLM_URL", "http://127.0.0.1:8001") + "/health"),
            "weights_present": args.diffusiongemma_path.is_file(),
        },
    }
    serialized = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
