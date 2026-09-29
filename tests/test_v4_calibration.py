import json

import pytest

from dicojev.calibration import (
    CalibrationRecord,
    LogisticCoverageEstimator,
    PlattCalibrator,
    calibration_metrics,
    dataset_sha256,
    records_from_jsonl,
    reliability_curve,
)


def records():
    return [
        CalibrationRecord(
            case_id=f"case-{index}",
            split="train" if index < 4 else "validation",
            coverage_raw=raw,
            adequate=label,
            features={"candidate_count": count, "max_similarity": similarity},
        )
        for index, (raw, label, count, similarity) in enumerate(
            [
                (0.10, False, 1, 0.1),
                (0.25, False, 2, 0.2),
                (0.75, True, 3, 0.8),
                (0.90, True, 4, 0.9),
                (0.20, False, 1, 0.2),
                (0.80, True, 4, 0.8),
            ]
        )
    ]


def test_calibration_dataset_is_strict_and_hash_is_stable():
    data = records()
    assert dataset_sha256(data) == dataset_sha256(data)
    lines = [json.dumps(record.model_dump(mode="json")) for record in data]
    assert records_from_jsonl(lines) == data


def test_platt_calibration_fits_and_versions_artifact():
    data = records()
    train, validation = data[:4], data[4:]
    calibrator = PlattCalibrator.fit(
        [record.coverage_raw for record in train], [record.adequate for record in train]
    )
    assert calibrator.predict(0.9) > calibrator.predict(0.1)
    artifact = calibrator.artifact(data, validation, model_version="fixture-v1")
    assert artifact.kind == "platt"
    assert artifact.validation_metrics.count == 2
    assert len(artifact.dataset_sha256) == 64
    restored = PlattCalibrator.from_artifact(artifact)
    assert restored.predict(0.9) == pytest.approx(calibrator.predict(0.9))


def test_logistic_coverage_estimator_learns_held_out_ordering():
    data = records()
    estimator = LogisticCoverageEstimator.fit(
        data[:4], feature_names=("candidate_count", "max_similarity")
    )
    assert estimator.predict(data[5].features) > estimator.predict(data[4].features)
    artifact = estimator.artifact(data, data[4:], model_version="coverage-v1")
    assert artifact.feature_names == ("candidate_count", "max_similarity")
    assert artifact.validation_metrics.brier < 0.25
    restored = LogisticCoverageEstimator.from_artifact(artifact)
    assert restored.predict(data[5].features) == pytest.approx(estimator.predict(data[5].features))


def test_calibration_metrics_keep_accuracy_separate_from_confidence():
    metrics = calibration_metrics([0.1, 0.9], [False, True], bins=2)
    assert metrics.brier == pytest.approx(0.01)
    assert metrics.expected_calibration_error == pytest.approx(0.1)
    assert reliability_curve([0.1, 0.9], [False, True], bins=2) == [
        {
            "bin_lower": 0.0,
            "bin_upper": 0.5,
            "count": 1,
            "mean_confidence": 0.1,
            "empirical_accuracy": 0.0,
        },
        {
            "bin_lower": 0.5,
            "bin_upper": 1.0,
            "count": 1,
            "mean_confidence": 0.9,
            "empirical_accuracy": 1.0,
        },
    ]


def test_calibration_rejects_mismatched_or_empty_inputs():
    with pytest.raises(ValueError):
        PlattCalibrator.fit([], [])
    with pytest.raises(ValueError):
        calibration_metrics([0.5], [])
