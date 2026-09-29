"""Execute matched feedback policies through Mercury generation and hosted Jev reads."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from dicojev.backends import JevCloudBackend
from dicojev.controller import ThresholdRiskController
from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import MercuryGenerator
from dicojev.harness import DecisionOrchestrator, canonical_action
from dicojev.schemas import (
    Candidate,
    DecisionBudget,
    DecisionRequest,
    DecisionSpec,
    FeedbackCode,
    GenerationFeedback,
    GeneratorCapabilities,
    LoopContext,
    MultimodalState,
)
from dicojev.v4 import CostAwareRiskController, FeedbackRecoveryPolicy, RecoveryObservation

DEFAULT_DATASET = Path(__file__).parents[1] / "benchmarks" / "v1_text_decisions.json"


class SeedThenMercury:
    capabilities = GeneratorCapabilities()

    def __init__(self, seed: list[str], mercury: MercuryGenerator) -> None:
        self.seed = seed
        self.mercury = mercury

    async def generate(
        self, request: DecisionRequest, context: LoopContext | None = None
    ) -> DecisionSpec:
        if context is not None:
            return await self.mercury.generate(request, context)
        return DecisionSpec(
            task=request.goal,
            candidates=tuple(Candidate(action=action) for action in self.seed),
            selection_instruction="Choose the safest useful next action.",
            coverage_instruction="Is at least one acceptable action available?",
            constraints=request.constraints,
        )


class PolicyCompiler:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.typed = DeterministicFeedbackCompiler()

    async def compile(self, feedback) -> GenerationFeedback:
        typed = await self.typed.compile(feedback)
        if self.kind == "typed":
            return typed
        if self.kind == "binary_retry":
            instruction = "The prior set was inadequate. Try once more."
        else:
            instruction = (
                "The previous candidate set did not contain a sufficiently safe and useful "
                "action. Reconsider the observation, goal, constraints, declared tools, and all "
                "existing candidates. Preserve useful prior candidates, avoid paraphrases, do not "
                "invent missing facts, and generate materially different alternatives that could "
                "satisfy every constraint and resolve the omission identified by the evaluator."
            )
        return typed.model_copy(
            update={
                "instruction": instruction,
                "serialized_bytes": len(instruction.encode()),
                "prompt_tokens": len(instruction.split()),
            }
        )


async def run_case(
    case: dict[str, Any],
    policy: str,
    *,
    controller=None,
    max_expansions: int = 1,
) -> dict[str, Any]:
    acceptable = {canonical_action(action) for action in case["acceptable_actions"]}
    seed = [action for action in case["candidates"] if canonical_action(action) not in acceptable]
    mercury = MercuryGenerator(timeout_seconds=120)
    response = await DecisionOrchestrator(
        SeedThenMercury(seed, mercury),
        JevCloudBackend(timeout_seconds=120),
        controller or ThresholdRiskController(),
        PolicyCompiler(policy),
    ).run(
        DecisionRequest(
            state=MultimodalState(text=case["observation"]),
            goal=case["goal"],
            constraints=tuple(case["constraints"]),
            budget=DecisionBudget(max_candidates=6, max_expansions=max_expansions),
        )
    )
    return {
        "case_id": case["id"],
        "policy": policy,
        "final_action": response.action.value,
        "recovered": response.action.value == "ACT",
        "rounds": len(response.trace),
        "candidate_actions": [candidate.action for candidate in response.candidates],
        "feedback_tokens": sum(event.compiled_feedback_prompt_tokens for event in response.trace),
        "feedback_bytes": sum(event.feedback_serialized_bytes for event in response.trace),
        "latency_ms": response.total_latency_ms,
        "compute_units": response.total_compute_units,
        "mercury_usage": mercury.last_usage,
        "trace": [event.model_dump(mode="json") for event in response.trace],
    }


async def evaluate(dataset: Path) -> dict[str, Any]:
    cases = json.loads(dataset.read_text(encoding="utf-8"))
    policies = ("typed", "binary_retry", "long_form")
    rows = [await run_case(case, policy) for policy in policies for case in cases]
    table = {}
    for policy in policies:
        members = [row for row in rows if row["policy"] == policy]
        recovered = sum(row["recovered"] for row in members)
        tokens = sum(row["feedback_tokens"] for row in members)
        table[policy] = {
            "cases": len(members),
            "recovery_rate": recovered / len(members),
            "mean_feedback_tokens": tokens / len(members),
            "recoveries_per_100_tokens": 100 * recovered / tokens if tokens else 0.0,
            "mean_latency_ms": sum(row["latency_ms"] for row in members) / len(members),
            "mean_compute_units": sum(row["compute_units"] for row in members) / len(members),
        }
    typed = [row for row in rows if row["policy"] == "typed"]
    learned_policy = FeedbackRecoveryPolicy.fit(
        [
            RecoveryObservation(
                FeedbackCode.MISSING_ACTION,
                row["recovered"],
                row["feedback_tokens"],
            )
            for row in typed[:3]
        ]
    )
    fixed_one = [await run_case(case, "fixed_one", max_expansions=0) for case in cases]
    adaptive = [
        await run_case(
            case,
            "adaptive",
            controller=CostAwareRiskController(learned_policy, expansion_cost=0.5),
        )
        for case in cases
    ]

    def compute_summary(members: list[dict[str, Any]]) -> dict[str, float]:
        return {
            "risk": 1 - sum(row["recovered"] for row in members) / len(members),
            "mean_latency_ms": sum(row["latency_ms"] for row in members) / len(members),
            "mean_compute_units": sum(row["compute_units"] for row in members) / len(members),
            "mean_feedback_tokens": sum(row["feedback_tokens"] for row in members) / len(members),
            "expansion_rate": sum(row["rounds"] > 1 for row in members) / len(members),
        }

    return {
        "schema_version": "1",
        "evidence_class": "live_mercury_generation_and_jev_verification",
        "matched_cases": len(cases),
        "table": table,
        "rows": [*rows, *fixed_one, *adaptive],
        "adaptive_compute": {
            "learned_missing_action_recovery": learned_policy.recovery_probability(
                FeedbackCode.MISSING_ACTION
            ),
            "training_cases": [row["case_id"] for row in typed[:3]],
            "table": {
                "fixed_one_round": compute_summary(fixed_one),
                "fixed_two_round": compute_summary(typed),
                "adaptive": compute_summary(adaptive),
            },
        },
        "limitations": [
            "Recovery means the unchanged controller reached ACT after hosted Jev verification.",
            "The benchmark contains five small repository tasks and is not a broad ability claim.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.dataset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, indent=2, sort_keys=True)
    args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
