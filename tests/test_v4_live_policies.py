import asyncio
import importlib.util
from pathlib import Path

from dicojev.schemas import FeedbackBundle, FeedbackCode, FeedbackSignal


def load_evaluator():
    path = Path(__file__).parents[1] / "scripts" / "evaluate_v4_live_policies.py"
    spec = importlib.util.spec_from_file_location("evaluate_v4_live_policies", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_policy_compilers_emit_distinct_measured_payloads():
    evaluator = load_evaluator()
    feedback = FeedbackBundle(
        primary=FeedbackSignal(
            code=FeedbackCode.MISSING_ACTION,
            details={"requested_new_candidates": 2},
        ),
        source_round=0,
        controller_reason_code="coverage_below_threshold",
        generation_relevant=True,
    )
    compiled = [
        asyncio.run(evaluator.PolicyCompiler(kind).compile(feedback))
        for kind in ("typed", "binary_retry", "long_form")
    ]
    assert len({item.instruction for item in compiled}) == 3
    assert compiled[1].prompt_tokens < compiled[0].prompt_tokens < compiled[2].prompt_tokens
