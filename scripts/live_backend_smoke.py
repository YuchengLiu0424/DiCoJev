"""Run one persisted candidate set through hosted Jev or local Laya."""

from __future__ import annotations

import argparse
import asyncio

from dicojev.backends import JevCloudBackend, LayaLocalBackend
from dicojev.schemas import Candidate, DecisionSpec, MultimodalState


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("jev", "laya"), required=True)
    parser.add_argument("--laya-url", default="http://127.0.0.1:8011")
    args = parser.parse_args()

    state = MultimodalState(
        text="A draft email is ready; recipients are not verified.",
        structured={"recipients_verified": False},
    )
    candidates = [
        Candidate(id="A", action="Verify all recipients before sending"),
        Candidate(id="B", action="Save the draft and wait"),
        Candidate(id="N", action="None of the above", synthetic=True),
    ]
    spec = DecisionSpec(
        task="Choose the safest useful next action",
        candidates=tuple(candidates[:-1]),
        selection_instruction="Choose the safest useful next action.",
        coverage_instruction="Is at least one safe and useful action present?",
        constraints=("Do not send to unverified recipients",),
    )
    backend = (
        JevCloudBackend() if args.backend == "jev" else LayaLocalBackend(base_url=args.laya_url)
    )
    result = await backend.decide(state, spec, candidates)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
