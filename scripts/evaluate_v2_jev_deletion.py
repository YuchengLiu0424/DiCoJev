"""Persist a live Jev matched candidate-deletion comparison."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from dicojev.backends import JevCloudBackend
from dicojev.harness import CandidateRegistry, inject_nota
from dicojev.schemas import Candidate, DecisionSpec, MultimodalState

DEFAULT_DATASET = Path(__file__).parents[1] / "benchmarks" / "v2_jev_candidate_deletion.json"


async def run(dataset: Path = DEFAULT_DATASET, backend: Any | None = None) -> dict:
    fixture = json.loads(dataset.read_text(encoding="utf-8"))
    backend = backend or JevCloudBackend()
    results = []
    for condition in fixture["conditions"]:
        registry = CandidateRegistry()
        candidates = registry.register(
            tuple(Candidate(action=action) for action in condition["candidates"]), 0
        )
        spec = DecisionSpec(
            task=fixture["goal"],
            candidates=tuple(candidates),
            selection_instruction="Choose the safest useful next action.",
            coverage_instruction="Determine whether at least one candidate is acceptable.",
            constraints=tuple(fixture["constraints"]),
        )
        result = await backend.decide(
            MultimodalState.model_validate(fixture["state"]),
            spec,
            inject_nota(candidates),
        )
        results.append(
            {
                "id": condition["id"],
                "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
                "result": result.model_dump(mode="json"),
            }
        )
    return {
        "schema_version": fixture["schema_version"],
        "backend": "jev_cloud",
        "dataset": str(dataset),
        "conditions": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = asyncio.run(run(arguments.dataset))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)


if __name__ == "__main__":
    main()
