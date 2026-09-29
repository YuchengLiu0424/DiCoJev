"""Run one matched native binary-coverage and categorical-selection read."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path

from dicojev.backends import LladaHTTPNativeReadRuntime, NativeDLMDecisionBackend
from dicojev.schemas import Candidate, DecisionSpec, ImageRef, MultimodalState

RED_PIXEL_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--image", action="store_true", help="include a one-pixel red PNG")
    args = parser.parse_args()
    backend = NativeDLMDecisionBackend(
        LladaHTTPNativeReadRuntime(base_url=args.base_url, timeout_seconds=args.timeout),
        runtime_name="llada-v-local",
    )
    state = (
        MultimodalState(
            text="The image contains one red pixel.",
            images=(ImageRef(data=base64.b64decode(RED_PIXEL_PNG), media_type="image/png"),),
        )
        if args.image
        else MultimodalState(text="A draft email is ready but recipients are unverified.")
    )
    candidates = (
        [
            Candidate(id="A", action="Identify the image as red"),
            Candidate(id="N", action="None of the above", synthetic=True),
        ]
        if args.image
        else [
            Candidate(id="A", action="Verify the recipients before sending"),
            Candidate(id="N", action="None of the above", synthetic=True),
        ]
    )
    result = await backend.decide(
        state,
        DecisionSpec(
            task="Choose the safest useful next action",
            candidates=(),
            selection_instruction="Choose the safest useful action.",
            coverage_instruction="Is at least one acceptable action available?",
        ),
        candidates,
    )
    serialized = json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    asyncio.run(main())
