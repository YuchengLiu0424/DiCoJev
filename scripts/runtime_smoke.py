"""Health, initial-generation, and typed-feedback expansion smoke test."""

import argparse
import asyncio
import json
from pathlib import Path

from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import DEFAULT_MODEL, DiffusionGemmaGenerator, MercuryGenerator
from dicojev.harness import CandidateRegistry
from dicojev.schemas import (
    DecisionRequest,
    FeedbackBundle,
    FeedbackCode,
    FeedbackSignal,
    LoopContext,
    MultimodalState,
)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator", choices=("local", "mercury"), default="local")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    generator = (
        MercuryGenerator(timeout_seconds=args.timeout)
        if args.generator == "mercury"
        else DiffusionGemmaGenerator(
            base_url=args.base_url, model=args.model, timeout_seconds=args.timeout
        )
    )
    request = DecisionRequest(
        state=MultimodalState(text="A draft email is ready but recipients are unverified."),
        goal="Choose the safest useful next action",
    )
    initial = await generator.generate(request)
    initial_latency_ms = generator.last_latency_ms
    initial_usage = generator.last_usage
    registry = CandidateRegistry()
    prior = tuple(registry.register(initial.candidates, 0))
    bundle = FeedbackBundle(
        primary=FeedbackSignal(
            code=FeedbackCode.MISSING_ACTION,
            details={"requested_new_candidates": 2},
        ),
        source_round=0,
        controller_reason_code="smoke_low_coverage",
        generation_relevant=True,
    )
    compiled = await DeterministicFeedbackCompiler().compile(bundle)
    context = LoopContext(
        round_index=1,
        prior_candidates=prior,
        latest_feedback=bundle,
        generation_feedback=compiled,
        remaining_candidate_budget=max(0, request.budget.max_candidates - len(prior)),
        remaining_expansion_budget=0,
    )
    expansion = await generator.generate(request, context)
    report = {
        "generator": args.generator,
        "model": generator.model,
        "initial": {
            "candidates": [item.model_dump(mode="json") for item in initial.candidates],
            "latency_ms": initial_latency_ms,
            "usage": initial_usage,
        },
        "expansion": {
            "candidates": [item.model_dump(mode="json") for item in expansion.candidates],
            "latency_ms": generator.last_latency_ms,
            "usage": generator.last_usage,
            "feedback": compiled.model_dump(mode="json"),
        },
    }
    serialized = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    asyncio.run(main())
