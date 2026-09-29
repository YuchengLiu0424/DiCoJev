import importlib.util
from pathlib import Path

import pytest


def test_pearson_detects_aligned_and_opposed_scores():
    path = Path(__file__).parents[1] / "scripts" / "evaluate_v4_verifier_correlation.py"
    spec = importlib.util.spec_from_file_location("evaluate_v4_verifier_correlation", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.pearson([0.0, 0.5, 1.0], [0.0, 0.5, 1.0]) == pytest.approx(1.0)
    assert module.pearson([0.0, 0.5, 1.0], [1.0, 0.5, 0.0]) == pytest.approx(-1.0)
