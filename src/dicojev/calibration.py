"""CPU-only calibration and learned coverage utilities for v4 experiments."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from .schemas.models import StrictModel


def _sigmoid(value: float) -> float:
    if value >= 0:
        factor = math.exp(-value)
        return 1 / (1 + factor)
    factor = math.exp(value)
    return factor / (1 + factor)


def _logit(probability: float, epsilon: float = 1e-6) -> float:
    bounded = min(1 - epsilon, max(epsilon, probability))
    return math.log(bounded / (1 - bounded))


class CalibrationRecord(StrictModel):
    case_id: str = Field(min_length=1)
    split: Literal["train", "validation", "test"]
    coverage_raw: float = Field(ge=0, le=1)
    adequate: bool
    selection_confidence_raw: float | None = Field(default=None, ge=0, le=1)
    selected_acceptable: bool | None = None
    nota_selected: bool = False
    features: dict[str, float] = Field(default_factory=dict)


class CalibrationMetrics(StrictModel):
    count: int = Field(ge=0)
    brier: float = Field(ge=0)
    expected_calibration_error: float = Field(ge=0)


class CalibrationArtifact(StrictModel):
    schema_version: Literal["1"] = "1"
    kind: Literal["platt", "logistic_coverage"]
    model_version: str = Field(min_length=1)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    parameters: dict[str, float]
    feature_names: tuple[str, ...] = ()
    validation_metrics: CalibrationMetrics


def dataset_sha256(records: Sequence[CalibrationRecord]) -> str:
    payload = [record.model_dump(mode="json") for record in records]
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def calibration_metrics(
    probabilities: Sequence[float], labels: Sequence[bool], *, bins: int = 10
) -> CalibrationMetrics:
    if len(probabilities) != len(labels) or not probabilities:
        raise ValueError("probabilities and labels must have the same nonzero length")
    if bins < 1:
        raise ValueError("bins must be positive")
    brier = sum(
        (probability - float(label)) ** 2
        for probability, label in zip(probabilities, labels, strict=True)
    ) / len(labels)
    ece = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [
            position
            for position, probability in enumerate(probabilities)
            if low <= probability < high or (index == bins - 1 and probability == 1)
        ]
        if not members:
            continue
        confidence = sum(probabilities[position] for position in members) / len(members)
        accuracy = sum(float(labels[position]) for position in members) / len(members)
        ece += len(members) / len(labels) * abs(confidence - accuracy)
    return CalibrationMetrics(count=len(labels), brier=brier, expected_calibration_error=ece)


def reliability_curve(
    probabilities: Sequence[float], labels: Sequence[bool], *, bins: int = 10
) -> list[dict[str, float | int]]:
    if len(probabilities) != len(labels) or not probabilities:
        raise ValueError("probabilities and labels must have the same nonzero length")
    if bins < 1:
        raise ValueError("bins must be positive")
    curve = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [
            position
            for position, probability in enumerate(probabilities)
            if low <= probability < high or (index == bins - 1 and probability == 1)
        ]
        if members:
            curve.append(
                {
                    "bin_lower": low,
                    "bin_upper": high,
                    "count": len(members),
                    "mean_confidence": sum(probabilities[position] for position in members)
                    / len(members),
                    "empirical_accuracy": sum(float(labels[position]) for position in members)
                    / len(members),
                }
            )
    return curve


class PlattCalibrator:
    def __init__(self, slope: float = 1.0, intercept: float = 0.0) -> None:
        self.slope = slope
        self.intercept = intercept

    def predict(self, probability: float) -> float:
        return _sigmoid(self.slope * _logit(probability) + self.intercept)

    @classmethod
    def fit(
        cls,
        probabilities: Sequence[float],
        labels: Sequence[bool],
        *,
        learning_rate: float = 0.05,
        iterations: int = 1000,
        regularization: float = 1e-3,
    ) -> PlattCalibrator:
        if len(probabilities) != len(labels) or not probabilities:
            raise ValueError("probabilities and labels must have the same nonzero length")
        slope, intercept = 1.0, 0.0
        features = [_logit(probability) for probability in probabilities]
        for _ in range(iterations):
            predictions = [_sigmoid(slope * value + intercept) for value in features]
            slope_gradient = (
                sum(
                    (prediction - float(label)) * value
                    for prediction, label, value in zip(predictions, labels, features, strict=True)
                )
                / len(labels)
                + regularization * slope
            )
            intercept_gradient = sum(
                prediction - float(label)
                for prediction, label in zip(predictions, labels, strict=True)
            ) / len(labels)
            slope -= learning_rate * slope_gradient
            intercept -= learning_rate * intercept_gradient
        return cls(slope=slope, intercept=intercept)

    def artifact(
        self,
        records: Sequence[CalibrationRecord],
        validation: Sequence[CalibrationRecord],
        *,
        model_version: str,
    ) -> CalibrationArtifact:
        probabilities = [self.predict(record.coverage_raw) for record in validation]
        metrics = calibration_metrics(probabilities, [record.adequate for record in validation])
        return CalibrationArtifact(
            kind="platt",
            model_version=model_version,
            dataset_sha256=dataset_sha256(records),
            created_at=datetime.now(UTC),
            parameters={"slope": self.slope, "intercept": self.intercept},
            validation_metrics=metrics,
        )


class LogisticCoverageEstimator:
    def __init__(self, weights: Mapping[str, float], intercept: float = 0.0) -> None:
        self.weights = dict(weights)
        self.intercept = intercept

    def predict(self, features: Mapping[str, float]) -> float:
        value = self.intercept + sum(
            weight * float(features.get(name, 0.0)) for name, weight in self.weights.items()
        )
        return _sigmoid(value)

    @classmethod
    def fit(
        cls,
        records: Sequence[CalibrationRecord],
        *,
        feature_names: Sequence[str],
        learning_rate: float = 0.05,
        iterations: int = 1500,
        regularization: float = 1e-3,
    ) -> LogisticCoverageEstimator:
        if not records or not feature_names:
            raise ValueError("training records and feature names are required")
        weights = {name: 0.0 for name in feature_names}
        intercept = 0.0
        for _ in range(iterations):
            predictions = [
                _sigmoid(
                    intercept
                    + sum(weights[name] * record.features.get(name, 0.0) for name in feature_names)
                )
                for record in records
            ]
            for name in feature_names:
                gradient = (
                    sum(
                        (prediction - float(record.adequate)) * record.features.get(name, 0.0)
                        for prediction, record in zip(predictions, records, strict=True)
                    )
                    / len(records)
                    + regularization * weights[name]
                )
                weights[name] -= learning_rate * gradient
            intercept -= (
                learning_rate
                * sum(
                    prediction - float(record.adequate)
                    for prediction, record in zip(predictions, records, strict=True)
                )
                / len(records)
            )
        return cls(weights, intercept)

    def artifact(
        self,
        records: Sequence[CalibrationRecord],
        validation: Sequence[CalibrationRecord],
        *,
        model_version: str,
    ) -> CalibrationArtifact:
        probabilities = [self.predict(record.features) for record in validation]
        metrics = calibration_metrics(probabilities, [record.adequate for record in validation])
        return CalibrationArtifact(
            kind="logistic_coverage",
            model_version=model_version,
            dataset_sha256=dataset_sha256(records),
            created_at=datetime.now(UTC),
            parameters={"intercept": self.intercept, **self.weights},
            feature_names=tuple(self.weights),
            validation_metrics=metrics,
        )


def records_from_jsonl(lines: Iterable[str]) -> list[CalibrationRecord]:
    return [CalibrationRecord.model_validate_json(line) for line in lines if line.strip()]
