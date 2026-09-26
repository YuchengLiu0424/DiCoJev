# v1 Text Candidate-Set Evaluation

Date: 2026-09-27

## Scope

This is a small integration evaluation, not a statistical benchmark. It checks that identical,
persisted text candidate sets can be compiled and read by hosted Jev and local Laya, and that the
resulting evidence can be scored against human-auditable acceptable actions.

This suite remains the repository's fast smoke test as later versions mature. Published external
benchmarks are introduced progressively rather than replacing it; the staged policy and benchmark
order are defined in `EVALUATION.md`.

- Dataset: `benchmarks/v1_text_decisions.json`
- Cases: 5
- Candidates per case: 3
- Dataset SHA-256: `58c154a8cc5fda2d571a461dc807592a77e05781c289b5a118704984ba5f193e`
- Sources: one local DiffusionGemma compact-smoke output and four human fixtures
- Candidate order: fixed as stored in the dataset

Every set contains at least one acceptable action. Consequently, this run tests positive coverage
and selection behavior but cannot estimate false-adequate rate or coverage discrimination under
candidate omission.

## Results

| Backend | Acceptable selection | Preferred selection | Mean coverage | Coverage Brier | Mean read latency |
|---|---:|---:|---:|---:|---:|
| Jev Cloud | 5/5 (100%) | 4/5 (80%) | 0.9660 | 0.00118 | 1333.9 ms |
| Laya CPU | 2/5 (40%) | 2/5 (40%) | 0.7314 | 0.07880 | 1898.2 ms |

Jev usage was 503-533 input tokens and 61 output tokens per case. Laya reported 254-283 input
tokens and zero generated output tokens because its structured read is classification-style.
These provider token counts are not directly interchangeable.

Laya selected candidate `A` in all five fixed-order cases. That may indicate positional bias, but
five cases without order counterbalancing are insufficient to separate positional effects from
content preference. Its checkpoint also clamps an invalid choice temperature to 0.5, so its
confidence remains uncalibrated and is not compared numerically with Jev confidence.

## Reproduction

The runner validates the dataset for free and optionally calls either backend:

```bash
python scripts/evaluate_v1.py
python scripts/evaluate_v1.py --backend jev --output results/v1_jev.json
python scripts/evaluate_v1.py --backend laya --output results/v1_laya.json
```

The `results/` files are local run artifacts and are intentionally ignored. The committed dataset,
runner, tests, and hash make the input condition reproducible.

## Interpretation and next gate

This run closes the v1 integration question: both backends can read the same normalized candidate
sets, and the pipeline records backend-specific evidence, usage, and latency. It does not establish
a coverage-aware feedback advantage.

The next benchmark should enter v2 scope and add controlled candidate deletion, distractors,
constraint violations, deterministic candidate-order rotations, and an EXPAND recovery condition.
Those cases are required to measure false-adequate rate, wrong-ACT avoidance, positional
sensitivity, and typed-feedback recovery rather than only positive-set selection.
