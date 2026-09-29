"""Measure fixed-configuration native-read repeatability against an explicit tolerance."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dicojev.backends import LladaHTTPNativeReadRuntime, NativeDLMDecisionBackend
from dicojev.schemas import Candidate, DecisionSpec, MultimodalState


def summarize(runs: list[dict], tolerance: float) -> dict:
    if len(runs) < 2:
        raise ValueError("at least two runs are required")
    keys = ("coverage_logits", "selection_logits")
    spans = {
        key: [
            max(run[key][index] for run in runs) - min(run[key][index] for run in runs)
            for index in range(len(runs[0][key]))
        ]
        for key in keys
    }
    selected_ids = sorted({run["selected_id"] for run in runs})
    maximum = max(value for values in spans.values() for value in values)
    return {
        "runs": len(runs),
        "absolute_logit_tolerance": tolerance,
        "logit_spans": spans,
        "maximum_logit_span": maximum,
        "selected_ids": selected_ids,
        "pass": maximum <= tolerance and len(selected_ids) == 1,
    }


async def evaluate(base_url: str, repetitions: int, timeout: float, tolerance: float) -> dict:
    if repetitions < 2:
        raise ValueError("repetitions must be at least two")
    backend = NativeDLMDecisionBackend(
        LladaHTTPNativeReadRuntime(base_url=base_url, timeout_seconds=timeout),
        runtime_name="llada-v-local-fixed-sequential",
    )
    state = MultimodalState(text="A draft email is ready but recipients are unverified.")
    spec = DecisionSpec(
        task="Choose the safest useful next action",
        candidates=(),
        selection_instruction="Choose the safest useful action.",
        coverage_instruction="Is at least one acceptable action available?",
    )
    candidates = [
        Candidate(id="A", action="Verify the recipients before sending"),
        Candidate(id="N", action="None of the above", synthetic=True),
    ]
    runs = []
    for index in range(repetitions):
        result = await backend.decide(state, spec, candidates)
        runs.append(
            {
                "index": index + 1,
                "latency_ms": result.latency_ms,
                "coverage": result.coverage.raw,
                "coverage_logits": result.diagnostics["coverage_logits"],
                "selected_id": result.selection.selected_id,
                "selection_confidence": result.selection.confidence_raw,
                "selection_logits": result.diagnostics["selection_logits"],
            }
        )
    return {
        "schema_version": "1",
        "configuration": {
            "runtime": "LLaDA-V 8.43B local CPU",
            "read_mode": "sequential",
            "state": state.text,
            "candidate_ids": [candidate.id for candidate in candidates],
        },
        "summary": summarize(runs, tolerance),
        "runs": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.base_url, args.repetitions, args.timeout, args.tolerance))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, indent=2, sort_keys=True)
    args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if not report["summary"]["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
