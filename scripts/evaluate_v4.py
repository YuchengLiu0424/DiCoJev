"""Recreate the deterministic controlled v4 calibration and adaptive-compute report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from dicojev.calibration import (
    CalibrationRecord,
    LogisticCoverageEstimator,
    PlattCalibrator,
    calibration_metrics,
    dataset_sha256,
    reliability_curve,
)
from dicojev.schemas import FeedbackCode
from dicojev.v4 import (
    FeedbackRecoveryPolicy,
    RecoveryObservation,
    conformal_coverage_threshold,
    risk_latency_token_curve,
)

FEATURE_NAMES = (
    "candidate_count",
    "max_similarity",
    "unique_ratio",
    "constraint_compliance",
)
ARTIFACT_TIME = datetime(2026, 9, 29, tzinfo=UTC)


def code_revision() -> str:
    root = Path(__file__).parents[1]
    digest = hashlib.sha256()
    for path in (root / "src/dicojev/calibration.py", Path(__file__)):
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _bounded(value: float) -> float:
    return min(0.98, max(0.02, value))


def build_records() -> list[CalibrationRecord]:
    """Build a fixed candidate-set dataset with nontrivial calibration error."""
    records = []
    for index in range(90):
        count = 1 + index % 5
        similarity = (3 + (index * 7) % 17) / 20
        unique_ratio = (count - (1 if index % 7 == 0 else 0)) / count
        compliance = 0.5 if index % 11 == 0 else 1.0
        adequate = count >= 3 and similarity >= 0.55 and unique_ratio >= 0.75 and compliance == 1
        # Deliberately overconfident same-backbone score, suitable for a calibration fixture.
        raw = _bounded(
            0.25
            + 0.115 * count
            + 0.32 * similarity
            + 0.08 * unique_ratio
            + 0.08 * compliance
            + (0.08 if index % 4 == 0 else -0.02)
        )
        split = "train" if index < 50 else "validation" if index < 70 else "test"
        records.append(
            CalibrationRecord(
                case_id=f"controlled-{index:03d}",
                split=split,
                coverage_raw=raw,
                adequate=adequate,
                selection_confidence_raw=_bounded(raw - 0.04 + (index % 3) * 0.025),
                selected_acceptable=adequate or index % 9 != 0,
                nota_selected=not adequate and raw < 0.76,
                features={
                    "candidate_count": float(count),
                    "max_similarity": similarity,
                    "unique_ratio": unique_ratio,
                    "constraint_compliance": compliance,
                },
            )
        )
    return records


def _pearson(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_scale = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    return numerator / (left_scale * right_scale)


def _feedback_comparison() -> dict:
    rows = {
        "typed": [(True, 12), (True, 11), (True, 13), (False, 12), (True, 12)],
        "binary_retry": [(True, 4), (False, 4), (True, 4), (False, 4), (False, 4)],
        "long_form": [(True, 80), (True, 76), (True, 84), (True, 82), (False, 78)],
    }
    table = {}
    for name, observations in rows.items():
        recovered = sum(item[0] for item in observations)
        tokens = sum(item[1] for item in observations)
        table[name] = {
            "cases": len(observations),
            "recovery_rate": recovered / len(observations),
            "mean_feedback_tokens": tokens / len(observations),
            "recoveries_per_100_tokens": 100 * recovered / tokens,
        }
    policy = FeedbackRecoveryPolicy.fit(
        [
            RecoveryObservation(FeedbackCode.MISSING_ACTION, recovered, tokens)
            for recovered, tokens in rows["typed"]
        ]
    )
    return {
        "table": table,
        "learned_missing_action_probability": policy.recovery_probability(
            FeedbackCode.MISSING_ACTION
        ),
        "learned_missing_action_token_cost": policy.expected_token_cost(
            FeedbackCode.MISSING_ACTION
        ),
    }


def _compute_comparison(test: list[CalibrationRecord], learned: list[float]) -> dict:
    policies = {
        "fixed_two_round": lambda _record, _probability: True,
        "fixed_one_round": lambda _record, _probability: False,
        "adaptive": lambda record, probability: record.coverage_raw < 0.9 and probability < 0.55,
    }
    table = {}
    curve_rows = []
    for name, should_expand in policies.items():
        errors = 0
        total_latency = 0.0
        total_tokens = 0.0
        expansions = 0
        for record, probability in zip(test, learned, strict=True):
            expanded = should_expand(record, probability)
            expansions += int(expanded)
            latency = 28.0 + (42.0 if expanded else 0.0)
            tokens = 18.0 + (12.0 if expanded else 0.0)
            # Controlled expansion fixes adequate-but-low-score sets and half of inadequate sets.
            success = record.adequate or (expanded and int(record.case_id[-1]) % 2 == 0)
            errors += int(not success)
            total_latency += latency
            total_tokens += tokens
            curve_rows.append(
                {
                    "coverage_threshold": {
                        "fixed_one_round": 0.0,
                        "adaptive": 0.82,
                        "fixed_two_round": 1.0,
                    }[name],
                    "error": not success,
                    "latency_ms": latency,
                    "tokens": tokens,
                }
            )
        table[name] = {
            "risk": errors / len(test),
            "mean_latency_ms": total_latency / len(test),
            "mean_tokens": total_tokens / len(test),
            "expansion_rate": expansions / len(test),
        }
    return {"table": table, "risk_latency_token_curve": risk_latency_token_curve(curve_rows)}


def evaluate() -> dict:
    records = build_records()
    train = [record for record in records if record.split == "train"]
    validation = [record for record in records if record.split == "validation"]
    test = [record for record in records if record.split == "test"]
    platt = PlattCalibrator.fit(
        [record.coverage_raw for record in train], [record.adequate for record in train]
    )
    estimator = LogisticCoverageEstimator.fit(train, feature_names=FEATURE_NAMES)
    labels = [record.adequate for record in test]
    raw = [record.coverage_raw for record in test]
    calibrated = [platt.predict(value) for value in raw]
    independent = [estimator.predict(record.features) for record in test]
    raw_metrics = calibration_metrics(raw, labels)
    calibrated_metrics = calibration_metrics(calibrated, labels)
    independent_metrics = calibration_metrics(independent, labels)
    adequate_validation = [
        platt.predict(record.coverage_raw) for record in validation if record.adequate
    ]
    threshold = conformal_coverage_threshold(adequate_validation, miscoverage=0.1)
    nota_rows = [record for record in test if record.nota_selected]
    inadequate = [record for record in test if not record.adequate]
    calibration_ablation = {
        "raw_brier": raw_metrics.brier,
        "platt_brier": calibrated_metrics.brier,
        "brier_improvement": raw_metrics.brier - calibrated_metrics.brier,
    }
    quality_only = [
        estimator.predict(
            {
                "candidate_count": 0.0,
                "max_similarity": 0.0,
                "unique_ratio": record.features["unique_ratio"],
                "constraint_compliance": record.features["constraint_compliance"],
            }
        )
        for record in test
    ]
    return {
        "schema_version": "1",
        "evidence_class": "deterministic_controlled_fixture",
        "limitations": [
            "No result in this artifact is a live-model performance estimate.",
            "Latency and token values are controlled accounting fixtures, not wall-clock measurements.",
        ],
        "dataset": {
            "sha256": dataset_sha256(records),
            "records": len(records),
            "splits": {"train": len(train), "validation": len(validation), "test": len(test)},
            "adequate_rate": sum(record.adequate for record in records) / len(records),
        },
        "calibration": {
            "raw": raw_metrics.model_dump(mode="json"),
            "platt": calibrated_metrics.model_dump(mode="json"),
            "learned_independent_verifier": independent_metrics.model_dump(mode="json"),
            "reliability_curves": {
                "raw": reliability_curve(raw, labels, bins=5),
                "platt": reliability_curve(calibrated, labels, bins=5),
                "learned_independent_verifier": reliability_curve(independent, labels, bins=5),
            },
            "platt_artifact": platt.artifact(
                records,
                validation,
                model_version="controlled-same-backbone-v1",
                code_revision=code_revision(),
                created_at=ARTIFACT_TIME,
            ).model_dump(mode="json"),
            "coverage_estimator_artifact": estimator.artifact(
                records,
                validation,
                model_version="controlled-independent-v1",
                code_revision=code_revision(),
                created_at=ARTIFACT_TIME,
            ).model_dump(mode="json"),
        },
        "dependence": {
            "same_backbone_vs_independent_pearson": _pearson(raw, independent),
            "same_backbone_vs_label_pearson": _pearson(raw, [float(value) for value in labels]),
            "independent_vs_label_pearson": _pearson(
                independent, [float(value) for value in labels]
            ),
        },
        "nota": {
            "test_inadequate_cases": len(inadequate),
            "nota_selected": len(nota_rows),
            "inadequate_detection_rate": len(nota_rows) / len(inadequate),
        },
        "conformal_vs_repeated_generation": {
            "conformal_threshold": threshold,
            "validation_miscoverage_target": 0.1,
            "test_accept_rate": sum(value >= threshold for value in calibrated) / len(test),
            "repeated_generation_fixed_extra_rounds": len(test),
            "conformal_triggered_extra_rounds": sum(value < threshold for value in calibrated),
        },
        "feedback": _feedback_comparison(),
        "adaptive_compute": _compute_comparison(test, independent),
        "ablations": {
            "coverage_calibration": calibration_ablation,
            "candidate_quality_only": calibration_metrics(quality_only, labels).model_dump(
                mode="json"
            ),
            "feedback_removed": _feedback_comparison()["table"]["binary_retry"],
        },
        "controlled_corruptions": {
            "adequate": {"adequate": True, "expected_effect": "baseline"},
            "acceptable_deleted": {"adequate": False, "expected_effect": "coverage decreases"},
            "duplicate_added": {"adequate": True, "expected_effect": "unique_ratio decreases"},
            "distractor_added": {
                "adequate": True,
                "expected_effect": "selection entropy increases",
            },
        },
    }


def write_curve_svg(rows: list[dict[str, float]], output: Path) -> None:
    """Render a dependency-free risk/latency/token comparison from report rows."""
    width, height, margin = 720, 420, 55
    plot_width, plot_height = width - 2 * margin, height - 2 * margin
    max_latency = max(row["mean_latency_ms"] for row in rows)
    points = [
        (
            margin + row["mean_latency_ms"] / max_latency * plot_width,
            height - margin - row["risk"] * plot_height,
            row,
        )
        for row in rows
    ]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _row in points)
    circles = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{4 + row["mean_tokens"] / 10:.1f}" '
        f'fill="#2563eb"><title>risk={row["risk"]:.2f}, latency={row["mean_latency_ms"]:.1f}, '
        f"tokens={row['mean_tokens']:.1f}</title></circle>"
        for x, y, row in points
    )
    labels = "".join(
        f'<text x="{x + 9:.1f}" y="{y - 8:.1f}" font-size="12">{row["coverage_threshold"]:.2f}</text>'
        for x, y, row in points
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/>
<text x="{width / 2}" y="24" text-anchor="middle" font-family="sans-serif" font-size="16">Controlled risk-latency-token curve</text>
<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="black"/>
<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" stroke="black"/>
<text x="{width / 2}" y="{height - 12}" text-anchor="middle" font-family="sans-serif" font-size="13">Mean latency (fixture ms)</text>
<text x="16" y="{height / 2}" text-anchor="middle" font-family="sans-serif" font-size="13" transform="rotate(-90 16 {height / 2})">Risk</text>
<polyline points="{polyline}" fill="none" stroke="#2563eb" stroke-width="2"/>
{circles}{labels}
</svg>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--curve-csv", type=Path)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args()
    report = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.curve_csv:
        args.curve_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.curve_csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=("coverage_threshold", "risk", "mean_latency_ms", "mean_tokens"),
            )
            writer.writeheader()
            writer.writerows(report["adaptive_compute"]["risk_latency_token_curve"])
    if args.plot:
        write_curve_svg(report["adaptive_compute"]["risk_latency_token_curve"], args.plot)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
