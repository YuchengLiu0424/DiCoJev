import asyncio
import importlib.util
from pathlib import Path


def test_v5_report_covers_actions_modalities_costs_and_cache_equivalence():
    path = Path(__file__).parents[1] / "scripts" / "evaluate_v5.py"
    spec = importlib.util.spec_from_file_location("evaluate_v5", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    report = asyncio.run(module.evaluate())
    assert report["passed"] == report["cases"]
    assert report["controller_actions"] == ["ABSTAIN", "ACT", "ESCALATE", "EXPAND"]
    assert report["multimodal_cases"] >= 1
    assert report["shared_runtime_measurements"]["equivalent_coverage"] is True
    assert report["shared_runtime_measurements"]["equivalent_selection"] is True
    assert report["feedback_tokens"]["total"] > 0
    execution = report["agent_execution"]["execution_trace"][0]
    assert execution["action"]["status"] == "executed"
    assert execution["state_before"] == {"approved": False}
    assert execution["state_after"] == {"approved": True}
    assert report["gpu_memory"]["status"] == "not_available"
