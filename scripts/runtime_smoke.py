"""Health, initial-generation, and typed-feedback expansion smoke test."""

import argparse
import asyncio

import httpx

from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import DEFAULT_MODEL, DiffusionGemmaGenerator
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
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    async with httpx.AsyncClient(base_url=args.base_url, timeout=10) as client:
        response = await client.get("/v1/models")
        response.raise_for_status()
    generator = DiffusionGemmaGenerator(base_url=args.base_url, model=args.model)
    request = DecisionRequest(
        state=MultimodalState(text="A draft email is ready but recipients are unverified."),
        goal="Choose the safest useful next action",
    )
    initial = await generator.generate(request)
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
    print(f"health=ok initial={len(initial.candidates)} expansion={len(expansion.candidates)}")


if __name__ == "__main__":
    asyncio.run(main())
