"""Run a task-held-out live Jev candidate-set corruption and calibration study."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from dicojev.backends import JevCloudBackend
from dicojev.calibration import CalibrationRecord, PlattCalibrator, calibration_metrics
from dicojev.harness import CandidateRegistry, canonical_action, inject_nota
from dicojev.schemas import Candidate, DecisionSpec, MultimodalState
from dicojev.v4 import candidate_set_features

DEFAULT_DATASET = Path(__file__).parents[1] / "benchmarks" / "v1_text_decisions.json"


def build_conditions(case: dict[str, Any]) -> list[dict[str, Any]]:
    acceptable = {canonical_action(action) for action in case["acceptable_actions"]}
    original = list(case["candidates"])
    deleted = [action for action in original if canonical_action(action) not in acceptable]
    return [
        {"name": "adequate", "actions": original, "adequate": True},
        {"name": "acceptable_deleted", "actions": deleted, "adequate": False},
        {
            "name": "duplicate_added",
            "actions": [*original, original[0]],
            "adequate": True,
        },
        {
            "name": "distractor_added",
            "actions": [*original, "Take an unrelated action"],
            "adequate": True,
        },
    ]


def split_for_case(index: int) -> str:
    return "train" if index < 3 else "validation" if index == 3 else "test"


async def evaluate(dataset: Path, backend: Any) -> dict[str, Any]:
    cases = json.loads(dataset.read_text(encoding="utf-8"))
    rows = []
    records = []
    provider_model = "unknown"
    for case_index, case in enumerate(cases):
        for condition in build_conditions(case):
            semantic = [Candidate(action=action) for action in condition["actions"]]
            candidates = CandidateRegistry().register(semantic, 0)
            result = await backend.decide(
                MultimodalState(text=case["observation"]),
                DecisionSpec(
                    task=case["goal"],
                    candidates=tuple(candidates),
                    selection_instruction=f"Choose the candidate that best achieves: {case['goal']}",
                    coverage_instruction=(
                        f"Determine whether at least one candidate acceptably achieves: {case['goal']}"
                    ),
                    constraints=tuple(case["constraints"]),
                ),
                inject_nota(candidates),
            )
            provider_model = result.diagnostics.get("model") or provider_model
            features = candidate_set_features(candidates)
            record = CalibrationRecord(
                case_id=f"{case['id']}:{condition['name']}",
                split=split_for_case(case_index),
                coverage_raw=result.coverage.raw,
                adequate=condition["adequate"],
                selection_confidence_raw=result.selection.confidence_raw,
                selected_acceptable=(
                    result.selection.selected_id != "N" if condition["adequate"] else False
                ),
                nota_selected=result.selection.selected_id == "N",
                features=features,
            )
            records.append(record)
            rows.append(
                {
                    **record.model_dump(mode="json"),
                    "condition": condition["name"],
                    "candidate_actions": condition["actions"],
                    "backend": result.backend,
                    "latency_ms": result.latency_ms,
                    "selected_id": result.selection.selected_id,
                    "usage": result.diagnostics.get("usage", {}),
                }
            )
    train = [record for record in records if record.split == "train"]
    validation = [record for record in records if record.split == "validation"]
    test = [record for record in records if record.split == "test"]
    calibrator = PlattCalibrator.fit(
        [record.coverage_raw for record in train], [record.adequate for record in train]
    )
    raw = [record.coverage_raw for record in test]
    calibrated = [calibrator.predict(value) for value in raw]
    labels = [record.adequate for record in test]
    deleted = [row for row in rows if row["condition"] == "acceptable_deleted"]
    adequate = [row for row in rows if row["condition"] == "adequate"]
    return {
        "schema_version": "1",
        "evidence_class": "live_hosted_jev_controlled_corruptions",
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "provider_model": provider_model,
        "task_disjoint_splits": {
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
        },
        "test_metrics": {
            "raw": calibration_metrics(raw, labels).model_dump(mode="json"),
            "platt": calibration_metrics(calibrated, labels).model_dump(mode="json"),
        },
        "calibration_artifact": calibrator.artifact(
            records, validation, model_version=str(provider_model)
        ).model_dump(mode="json"),
        "corruption_effects": {
            "mean_adequate_coverage": sum(row["coverage_raw"] for row in adequate) / len(adequate),
            "mean_deleted_coverage": sum(row["coverage_raw"] for row in deleted) / len(deleted),
            "deleted_nota_rate": sum(row["nota_selected"] for row in deleted) / len(deleted),
        },
        "limitations": [
            "Only five base tasks are available; the task-held-out test split contains one task.",
            "This evaluates hosted Jev evidence, not local Djev or native LLaDA calibration.",
        ],
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.dataset, JevCloudBackend(timeout_seconds=args.timeout)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, indent=2, sort_keys=True)
    args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
