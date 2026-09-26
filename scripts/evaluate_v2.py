"""Run and persist the deterministic v2 controlled closed-loop report."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from dicojev.backends import MockDecisionBackend
from dicojev.controller import ThresholdRiskController
from dicojev.escalation import MockEscalationTarget
from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import FakeCandidateGenerator
from dicojev.harness import DecisionOrchestrator
from dicojev.schemas import (
    BackendCapabilities,
    Candidate,
    CoverageScore,
    DecisionBackendResult,
    DecisionBudget,
    DecisionRequest,
    MultimodalState,
    SelectionScore,
)

DEFAULT_DATASET = Path(__file__).parents[1] / "benchmarks" / "v2_controlled.json"


def load_cases(path: Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("v2 dataset must be a non-empty list")
    return payload


def _backend_result(payload: dict[str, Any]) -> DecisionBackendResult:
    if "coverage" not in payload:
        return DecisionBackendResult(backend="mock")
    probabilities = payload["probabilities"]
    selected = payload["selected"]
    return DecisionBackendResult(
        backend="mock",
        coverage=CoverageScore(raw=payload["coverage"], method="controlled_fixture"),
        selection=SelectionScore(
            selected_id=selected,
            probabilities=probabilities,
            confidence_raw=probabilities[selected],
        ),
    )


async def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    state = MultimodalState.model_validate(case["state"])
    request = DecisionRequest(
        state=state,
        goal=case["goal"],
        available_tools=tuple(case.get("available_tools", ())),
        constraints=tuple(case.get("constraints", ())),
        budget=DecisionBudget.model_validate(case["budget"]),
    )
    rounds = [
        tuple(Candidate.model_validate(item) for item in items) for items in case["candidates"]
    ]
    capabilities = BackendCapabilities(
        supports_images=bool(state.images),
        supports_native_multimodal=bool(state.images),
    )
    response = await DecisionOrchestrator(
        FakeCandidateGenerator(rounds),
        MockDecisionBackend(
            [_backend_result(item) for item in case["backend"]],
            capabilities=capabilities,
        ),
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
        MockEscalationTarget(),
    ).run(request)
    observed_feedback = [code.value for event in response.trace for code in event.feedback_codes]
    passed = response.action.value == case["expected_action"]
    if expected := case.get("expected_feedback"):
        passed = passed and expected in observed_feedback
    return {
        "id": case["id"],
        "passed": passed,
        "expected_action": case["expected_action"],
        "action": response.action.value,
        "feedback_codes": observed_feedback,
        "rounds": [event.model_dump(mode="json") for event in response.trace],
        "total_latency_ms": response.total_latency_ms,
        "total_compute_units": response.total_compute_units,
    }


async def run(path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    cases = [await evaluate_case(case) for case in load_cases(path)]
    controller_actions = sorted(
        {round_["controller_action"] for case in cases for round_ in case["rounds"]}
    )
    return {
        "schema_version": "v2-controlled-1",
        "summary": {
            "cases": len(cases),
            "passed": sum(case["passed"] for case in cases),
            "final_actions": sorted({case["action"] for case in cases}),
            "controller_actions": controller_actions,
        },
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = asyncio.run(run(arguments.dataset))
    serialized = json.dumps(report, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
