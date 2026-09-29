from pathlib import Path

import pytest

from dicojev.backends import MockDecisionBackend
from dicojev.schemas import CoverageScore, DecisionBackendResult, SelectionScore
from scripts.evaluate_v2 import DEFAULT_DATASET, load_cases, run
from scripts.evaluate_v2_jev_deletion import DEFAULT_DATASET as JEV_DELETION_DATASET
from scripts.evaluate_v2_jev_deletion import run as run_jev_deletion


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
    assert (
        by_id["all-gold-deleted"]["rounds"][0]["coverage_raw"]
        < by_id["adequate"]["rounds"][0]["coverage_raw"]
    )


@pytest.mark.asyncio
async def test_live_jev_deletion_runner_persists_matched_normalized_results():
    backend = MockDecisionBackend(
        [
            DecisionBackendResult(
                backend="jev_cloud",
                coverage=CoverageScore(raw=0.98, method="noul_probability"),
                selection=SelectionScore(
                    selected_id="A",
                    probabilities={"A": 0.98, "B": 0.01, "N": 0.01},
                    confidence_raw=0.98,
                ),
            ),
            DecisionBackendResult(
                backend="jev_cloud",
                coverage=CoverageScore(raw=0.15, method="noul_probability"),
                selection=SelectionScore(
                    selected_id="N",
                    probabilities={"A": 0.05, "B": 0.10, "N": 0.85},
                    confidence_raw=0.85,
                ),
            ),
        ]
    )
    report = await run_jev_deletion(JEV_DELETION_DATASET, backend)
    assert [item["id"] for item in report["conditions"]] == [
        "adequate",
        "all-acceptable-deleted",
    ]
    assert report["conditions"][0]["result"]["coverage"]["raw"] == 0.98
    assert report["conditions"][1]["result"]["selection"]["selected_id"] == "N"
