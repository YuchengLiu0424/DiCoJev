import importlib.util
from pathlib import Path


def load_evaluator():
    path = Path(__file__).parents[1] / "scripts" / "evaluate_v4_live_jev.py"
    spec = importlib.util.spec_from_file_location("evaluate_v4_live_jev", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_live_jev_conditions_are_controlled_and_task_splits_are_disjoint():
    evaluator = load_evaluator()
    case = {
        "candidates": ["safe", "unsafe"],
        "acceptable_actions": ["safe"],
    }
    conditions = evaluator.build_conditions(case)
    assert [condition["name"] for condition in conditions] == [
        "adequate",
        "acceptable_deleted",
        "duplicate_added",
        "distractor_added",
    ]
    assert conditions[1] == {
        "name": "acceptable_deleted",
        "actions": ["unsafe"],
        "adequate": False,
    }
    assert [evaluator.split_for_case(index) for index in range(5)] == [
        "train",
        "train",
        "train",
        "validation",
        "test",
    ]
