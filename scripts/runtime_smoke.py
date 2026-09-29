"""Health, initial-generation, and typed-feedback expansion smoke test."""

import argparse
import asyncio
import json
from pathlib import Path

from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import (
    DEFAULT_LLADA_MODEL,
    DEFAULT_MODEL,
    DiffusionGemmaGenerator,
    LladaGenerator,
    MercuryGenerator,
)
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
    parser.add_argument(
        "--generator", choices=("diffusiongemma", "llada", "mercury", "local"), default="local"
    )
    parser.add_argument("--base-url")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--max-completion-tokens", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.generator == "mercury":
        generator = MercuryGenerator(timeout_seconds=args.timeout)
    elif args.generator == "llada":
        generator = LladaGenerator(
            base_url=args.base_url or "http://127.0.0.1:8002",
            model=args.model if args.model != DEFAULT_MODEL else DEFAULT_LLADA_MODEL,
            timeout_seconds=args.timeout,
            max_completion_tokens=args.max_completion_tokens or 32,
        )
    else:
        generator = DiffusionGemmaGenerator(
            base_url=args.base_url or "http://127.0.0.1:8000",
            model=args.model,
            timeout_seconds=args.timeout,
            max_completion_tokens=args.max_completion_tokens,
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
