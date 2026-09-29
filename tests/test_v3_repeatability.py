import importlib.util
from pathlib import Path

import pytest


def load_evaluator():
    path = Path(__file__).parents[1] / "scripts" / "evaluate_v3_repeatability.py"
    spec = importlib.util.spec_from_file_location("evaluate_v3_repeatability", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_repeatability_summary_enforces_logits_and_decision_tolerance():
    summarize = load_evaluator().summarize
    runs = [
        {"coverage_logits": [1.0, 2.0], "selection_logits": [3.0, 1.0], "selected_id": "A"},
        {
            "coverage_logits": [1.01, 1.99],
            "selection_logits": [3.01, 1.0],
            "selected_id": "A",
        },
    ]
    assert summarize(runs, 0.02)["pass"] is True
    runs[1]["selected_id"] = "N"
    assert summarize(runs, 0.02)["pass"] is False
    with pytest.raises(ValueError):
        summarize(runs[:1], 0.02)
