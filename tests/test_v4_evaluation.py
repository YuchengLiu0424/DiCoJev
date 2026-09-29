import importlib.util
from pathlib import Path


def load_evaluator():
    path = Path(__file__).parents[1] / "scripts" / "evaluate_v4.py"
    spec = importlib.util.spec_from_file_location("evaluate_v4", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v4_evaluation_is_complete_and_deterministic():
    evaluator = load_evaluator()
    first = evaluator.evaluate()
    second = evaluator.evaluate()
    assert first["dataset"] == second["dataset"]
    assert first["calibration"]["raw"] == second["calibration"]["raw"]
    assert first["calibration"]["platt"] == second["calibration"]["platt"]
    assert first["calibration"]["platt"]["brier"] < first["calibration"]["raw"]["brier"]
    assert set(first["feedback"]["table"]) == {"typed", "binary_retry", "long_form"}
    assert set(first["adaptive_compute"]["table"]) == {
        "fixed_two_round",
        "fixed_one_round",
        "adaptive",
    }
    compute = first["adaptive_compute"]["table"]
    assert 0 < compute["adaptive"]["expansion_rate"] < 1
    assert (
        compute["fixed_one_round"]["mean_latency_ms"]
        < compute["adaptive"]["mean_latency_ms"]
        < compute["fixed_two_round"]["mean_latency_ms"]
    )
    assert set(first["ablations"]) == {
        "coverage_calibration",
        "candidate_quality_only",
        "feedback_removed",
    }
