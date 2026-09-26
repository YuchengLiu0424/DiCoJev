import json
from argparse import Namespace
from pathlib import Path

import pytest

from dicojev.backends import MockDecisionBackend
from dicojev.schemas import CoverageScore, DecisionBackendResult, SelectionScore
from scripts.evaluate_v1 import DEFAULT_DATASET, evaluate_backend, load_cases, run


def backend_result(selected_id="A"):
    return DecisionBackendResult(
        backend="mock",
        coverage=CoverageScore(raw=0.9, method="fixture"),
        selection=SelectionScore(
            selected_id=selected_id,
            probabilities={selected_id: 1.0},
            confidence_raw=1.0,
        ),
        latency_ms=2.0,
    )


def test_v1_dataset_is_well_formed_and_contains_local_dlm_smoke():
    cases = load_cases(DEFAULT_DATASET)
    assert len(cases) == 5
    assert {case["source"] for case in cases} == {
        "human_fixture",
        "local_diffusiongemma_compact_smoke",
    }


def test_dataset_rejects_unlisted_acceptable_action(tmp_path: Path):
    invalid = [
        {
            "id": "x",
            "observation": "x",
            "goal": "x",
            "constraints": [],
            "candidates": ["A"],
            "acceptable_actions": ["B"],
            "preferred_action": "B",
            "source": "fixture",
        }
    ]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError, match="not in candidates"):
        load_cases(path)


@pytest.mark.asyncio
async def test_backend_evaluation_reports_reproducible_metrics():
    cases = load_cases(DEFAULT_DATASET)[:1]
    report = await evaluate_backend("mock", MockDecisionBackend([backend_result()]), cases)
    assert report["summary"]["coverage_brier"] == pytest.approx(0.01)
    assert report["summary"]["acceptable_selection_rate_given_coverage"] == 1.0
    assert report["cases"][0]["selected_action"] == "Verify email recipients"


@pytest.mark.asyncio
async def test_offline_run_validates_without_constructing_live_backends():
    report = await run(
        Namespace(
            dataset=DEFAULT_DATASET,
            backend="none",
            laya_url="http://127.0.0.1:8011",
            timeout=1,
        )
    )
    assert report["validation"]["cases"] == 5
    assert report["backends"] == {}
    assert len(report["dataset_sha256"]) == 64
