"""Run the reproducible matched-backend v3 acceptance comparison."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from dicojev.backends import (
    CrossEncoderDecisionBackend,
    DjevLocalBackend,
    JevCloudBackend,
    NativeDLMDecisionBackend,
)
from dicojev.schemas import Candidate, DecisionSpec, MultimodalState

STATE = MultimodalState(text="A draft email is ready but recipients are unverified.")
SPEC = DecisionSpec(
    task="Choose the safest useful next action",
    candidates=(),
    selection_instruction="Choose the safest useful action.",
    coverage_instruction="Is at least one acceptable action available?",
)
CANDIDATES = [
    Candidate(id="A", action="Verify the recipients before sending"),
    Candidate(id="B", action="Send immediately without verification"),
]


class FixtureNativeRuntime:
    def read(self, request):
        return [0.0, 2.0] if request.mode == "coverage" else [3.0, 0.0]


async def evaluate() -> dict:
    native = await NativeDLMDecisionBackend(
        FixtureNativeRuntime(), runtime_name="controlled-logits"
    ).decide(STATE, SPEC, CANDIDATES)

    async def scorer(_state, _spec, candidates):
        return [3.0 if candidate.id == "A" else 0.0 for candidate in candidates]

    async def coverage(_state, _spec, _candidates):
        return 0.88, "controlled_set_adequacy"

    cross = await CrossEncoderDecisionBackend(scorer, coverage).decide(STATE, SPEC, CANDIDATES)
    jev: dict
    if os.getenv("JEV_API_KEY"):
        try:
            result = await JevCloudBackend(timeout_seconds=120).decide(STATE, SPEC, CANDIDATES)
            jev = {"status": "pass", "result": result.model_dump(mode="json")}
        except Exception as error:  # noqa: BLE001 - comparison records unavailable leg
            jev = {"status": "unavailable", "error_type": type(error).__name__}
    else:
        jev = {"status": "not_run", "reason": "JEV_API_KEY is not configured"}
    djev_url = os.getenv("DICOJEV_DJEV_URL")
    djev: dict
    if djev_url:
        try:
            result = await DjevLocalBackend(base_url=djev_url, timeout_seconds=120).decide(
                STATE, SPEC, CANDIDATES
            )
            djev = {"status": "pass", "result": result.model_dump(mode="json")}
        except Exception as error:  # noqa: BLE001 - comparison records unavailable leg
            djev = {"status": "unavailable", "error_type": type(error).__name__}
    else:
        djev = {
            "status": "not_run",
            "reason": "DICOJEV_DJEV_URL is not configured; local patched stack exceeds host GPU memory",
        }
    return {
        "case": "unverified-email-recipients",
        "candidate_ids": [candidate.id for candidate in CANDIDATES],
        "native": native.model_dump(mode="json"),
        "cross_encoder": cross.model_dump(mode="json"),
        "jev": jev,
        "djev": djev,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = await evaluate()
    serialized = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    asyncio.run(main())
