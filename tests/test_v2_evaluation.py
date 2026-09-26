from pathlib import Path

import pytest

from scripts.evaluate_v2 import DEFAULT_DATASET, load_cases, run


def test_v2_fixture_matrix_contains_required_conditions():
    identifiers = {case["id"] for case in load_cases(DEFAULT_DATASET)}
    assert identifiers == {
        "adequate",
        "all-gold-deleted",
        "best-only-deleted",
        "distractor-heavy",
        "duplicate-heavy",
        "tool-mismatch",
        "constraint-failure",
        "nota-needed",
        "insufficient-information",
        "expansion-recovery",
        "ambiguous-multimodal",
    }


@pytest.mark.asyncio
async def test_v2_report_covers_gate_and_persists_round_details(tmp_path: Path):
    report = await run()
    assert report["summary"]["passed"] == report["summary"]["cases"] == 11
    assert report["summary"]["controller_actions"] == [
        "ABSTAIN",
        "ACT",
        "ESCALATE",
        "EXPAND",
    ]
    assert any(
        round_["controller_action"] == "EXPAND"
        for case in report["cases"]
        for round_ in case["rounds"]
    )
    assert all(
        {"candidate_quality", "feedback_serialized_bytes", "latency_ms", "compute_units"}
        <= set(round_)
        for case in report["cases"]
        for round_ in case["rounds"]
    )
    by_id = {case["id"]: case for case in report["cases"]}
    assert by_id["all-gold-deleted"]["rounds"][0]["coverage_raw"] < by_id["adequate"][
        "rounds"
    ][0]["coverage_raw"]

