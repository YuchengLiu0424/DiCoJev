"""Generate once with DiffusionGemma, then compare Jev and local Laya."""

from __future__ import annotations

import argparse
import asyncio
import json

from dicojev.backends import JevCloudBackend, LayaLocalBackend
from dicojev.generator import DiffusionGemmaGenerator
from dicojev.harness import CandidateRegistry
from dicojev.schemas import Candidate, DecisionRequest, MultimodalState


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator-url", default="http://127.0.0.1:11434")
    parser.add_argument("--generator-model", default="dicojev-diffusiongemma")
    parser.add_argument("--laya-url", default="http://127.0.0.1:8011")
    args = parser.parse_args()

    request = DecisionRequest(
        state=MultimodalState(
            text="A draft email is ready; recipients are not verified.",
            structured={"recipients_verified": False},
        ),
        goal="Choose the safest useful next action",
        constraints=("Do not send to unverified recipients",),
    )
    generator = DiffusionGemmaGenerator(
        base_url=args.generator_url,
        model=args.generator_model,
        timeout_seconds=900,
    )
    spec = await generator.generate(request)
    candidates = CandidateRegistry().register(spec.candidates, 0)
    candidates.append(Candidate(id="N", action="None of the above", synthetic=True))

    jev_result, laya_result = await asyncio.gather(
        JevCloudBackend(timeout_seconds=60).decide(request.state, spec, candidates),
        LayaLocalBackend(base_url=args.laya_url, timeout_seconds=60).decide(
            request.state, spec, candidates
        ),
    )
    report = {
        "generator": {
            "model": generator.model,
            "latency_ms": generator.last_latency_ms,
            "usage": generator.last_usage,
        },
        "decision_spec": spec.model_dump(mode="json"),
        "persisted_candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "jev": jev_result.model_dump(mode="json"),
        "laya": laya_result.model_dump(mode="json"),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
