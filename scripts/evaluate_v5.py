"""Recreate the offline v5 end-to-end acceptance report."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import statistics
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load_script(name: str, directory: str = "scripts"):
    path = ROOT / directory / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


async def evaluate() -> dict:
    tracemalloc.start()
    v2 = await load_script("evaluate_v2.py").run()
    demo_response = await load_script("v5_offline_agent.py", directory="examples").run_demo()
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    latencies = [case["total_latency_ms"] for case in v2["cases"]]
    feedback_tokens = [
        sum(round_["compiled_feedback_prompt_tokens"] for round_ in case["rounds"])
        for case in v2["cases"]
    ]
    actions = sorted({case["action"] for case in v2["cases"]})
    multimodal = [
        case for case in v2["cases"] if any(round_["image_count"] > 0 for round_ in case["rounds"])
    ]
    v3_native = json.loads((ROOT / "benchmarks/v3_native_read.json").read_text(encoding="utf-8"))
    return {
        "schema_version": "1",
        "evidence_class": "offline_end_to_end_acceptance_plus_prior_live_measurements",
        "cases": len(v2["cases"]),
        "passed": v2["summary"]["passed"],
        "controller_actions": v2["summary"]["controller_actions"],
        "final_actions": actions,
        "multimodal_cases": len(multimodal),
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "mean": statistics.fmean(latencies),
        },
        "feedback_tokens": {
            "total": sum(feedback_tokens),
            "mean_per_case": statistics.fmean(feedback_tokens),
        },
        "peak_python_memory_bytes": peak,
        "gpu_memory": {
            "status": "not_available",
            "reason": "Evaluation host is CPU-only; no model GPU allocation can be measured.",
        },
        "shared_runtime_measurements": {
            "native_image_uncached_ms": v3_native["native_image"]["latency_ms"],
            "native_image_cached_ms": v3_native["native_image_cached"]["latency_ms"],
            "improvement_percent": v3_native["native_image_cached"]["improvement_percent"],
            "equivalent_coverage": (
                v3_native["native_image"]["coverage"]
                == v3_native["native_image_cached"]["coverage"]
            ),
            "equivalent_selection": (
                v3_native["native_image"]["selected_id"]
                == v3_native["native_image_cached"]["selected_id"]
            ),
        },
        "risk_latency_token": json.loads(
            (ROOT / "benchmarks/v4_evaluation.json").read_text(encoding="utf-8")
        )["adaptive_compute"],
        "source_report": v2,
        "agent_execution": demo_response.model_dump(mode="json"),
        "limitations": [
            "Offline acceptance latency and Python memory are harness measurements, not model runtime measurements.",
            "Live model latency and policy results remain in the versioned v3/v4 artifacts.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(evaluate())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, indent=2, sort_keys=True)
    args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
