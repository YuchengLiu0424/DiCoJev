"""Evaluate persisted v1 text candidate sets with optional Jev/Laya reads."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from dicojev.backends import JevCloudBackend, LayaLocalBackend
from dicojev.harness import CandidateRegistry, canonical_action, inject_nota
from dicojev.schemas import Candidate, DecisionRequest, DecisionSpec, MultimodalState

DEFAULT_DATASET = Path(__file__).parents[1] / "benchmarks" / "v1_text_decisions.json"


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("evaluation dataset must be a non-empty JSON array")
    required = {
        "id",
        "observation",
        "goal",
        "constraints",
        "candidates",
        "acceptable_actions",
        "preferred_action",
        "source",
    }
    ids: set[str] = set()
    for case in payload:
        if not isinstance(case, dict) or set(case) != required:
            raise ValueError("each case must contain exactly the documented fields")
        if case["id"] in ids:
            raise ValueError(f"duplicate case id: {case['id']}")
        ids.add(case["id"])
        candidates = {canonical_action(value) for value in case["candidates"]}
        acceptable = {canonical_action(value) for value in case["acceptable_actions"]}
        if not acceptable <= candidates:
            raise ValueError(f"case {case['id']} has an acceptable action not in candidates")
        if canonical_action(case["preferred_action"]) not in acceptable:
            raise ValueError(f"case {case['id']} preferred action is not acceptable")
    return payload


def compile_case(case: dict[str, Any]) -> tuple[DecisionRequest, DecisionSpec, list[Candidate]]:
    request = DecisionRequest(
        state=MultimodalState(text=case["observation"]),
        goal=case["goal"],
        constraints=tuple(case["constraints"]),
    )
    semantic = tuple(Candidate(action=action) for action in case["candidates"])
    spec = DecisionSpec(
        task=request.goal,
        candidates=semantic,
        selection_instruction=(
            f"Choose the candidate that best achieves this goal: {request.goal}"
        ),
        coverage_instruction=(
            f"Determine whether at least one candidate acceptably achieves this goal: "
            f"{request.goal}"
        ),
        constraints=request.constraints,
    )
    persisted = CandidateRegistry().register(semantic, 0)
    return request, spec, inject_nota(persisted)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [row["latency_ms"] for row in rows]
    covered = [row for row in rows if row["oracle_covered"]]
    return {
        "cases": len(rows),
        "mean_coverage": statistics.fmean(row["coverage_raw"] for row in rows),
        "coverage_brier": statistics.fmean(row["coverage_brier"] for row in rows),
        "acceptable_selection_rate_given_coverage": (
            statistics.fmean(float(row["selected_acceptable"]) for row in covered)
            if covered
            else None
        ),
        "preferred_selection_rate_given_coverage": (
            statistics.fmean(float(row["selected_preferred"]) for row in covered)
            if covered
            else None
        ),
        "latency_ms": {
            "mean": statistics.fmean(latencies),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
        },
    }


async def evaluate_backend(name: str, backend: Any, cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for case in cases:
        request, spec, candidates = compile_case(case)
        result = await backend.decide(request.state, spec, candidates)
        if result.coverage is None or result.selection is None:
            raise ValueError(f"{name} returned incomplete evidence for {case['id']}")
        selected = next(
            (candidate for candidate in candidates if candidate.id == result.selection.selected_id),
            None,
        )
        selected_action = selected.action if selected and not selected.synthetic else None
        acceptable = {canonical_action(value) for value in case["acceptable_actions"]}
        oracle_covered = bool(acceptable)
        rows.append(
            {
                "case_id": case["id"],
                "oracle_covered": oracle_covered,
                "coverage_raw": result.coverage.raw,
                "coverage_brier": (result.coverage.raw - float(oracle_covered)) ** 2,
                "selected_id": result.selection.selected_id,
                "selected_action": selected_action,
                "selected_acceptable": (
                    selected_action is not None and canonical_action(selected_action) in acceptable
                ),
                "selected_preferred": (
                    selected_action is not None
                    and canonical_action(selected_action)
                    == canonical_action(case["preferred_action"])
                ),
                "latency_ms": result.latency_ms,
                "usage": result.diagnostics.get("usage", {}),
            }
        )
    return {"summary": summarize(rows), "cases": rows}


def validate_dataset(cases: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_counts = [len(case["candidates"]) for case in cases]
    return {
        "cases": len(cases),
        "all_candidate_sets_covered": all(case["acceptable_actions"] for case in cases),
        "mean_candidates": statistics.fmean(candidate_counts),
        "sources": dict(
            sorted(
                {
                    source: sum(case["source"] == source for case in cases)
                    for source in {case["source"] for case in cases}
                }.items()
            )
        ),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset_path = args.dataset.resolve()
    cases = load_cases(dataset_path)
    report: dict[str, Any] = {
        "schema_version": "1",
        "dataset": str(dataset_path),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "validation": validate_dataset(cases),
        "backends": {},
    }
    if args.backend in {"jev", "both"}:
        report["backends"]["jev"] = await evaluate_backend(
            "jev", JevCloudBackend(timeout_seconds=args.timeout), cases
        )
    if args.backend in {"laya", "both"}:
        report["backends"]["laya"] = await evaluate_backend(
            "laya",
            LayaLocalBackend(base_url=args.laya_url, timeout_seconds=args.timeout),
            cases,
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--backend", choices=("none", "jev", "laya", "both"), default="none")
    parser.add_argument("--laya-url", default="http://127.0.0.1:8011")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(run(args))
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
