# Benchmarks

Benchmark datasets, synthetic perturbations, run artifacts, and evaluation runners live here.

The authoritative experiment design and metric definitions live in:

`docs/research/EVALUATION.md`

Do not commit licensed/private raw datasets, user screenshots, credentials, or model weights. Small synthetic fixtures are preferred for repository tests.

## v1 text evaluation

`v1_text_decisions.json` contains five small, human-auditable personal-computer decision cases.
The email case persists the candidate set produced by the local DiffusionGemma compact smoke; the
other cases are explicitly marked human fixtures. These fixtures test backend reads, not DLM
generation quality.

Validate the dataset without any service or API cost:

```bash
python scripts/evaluate_v1.py
```

Run identical persisted candidate sets through Jev, Laya, or both:

```bash
python scripts/evaluate_v1.py --backend jev --output results/v1_jev.json
python scripts/evaluate_v1.py --backend laya --output results/v1_laya.json
python scripts/evaluate_v1.py --backend both --output results/v1_jev_laya.json
```

Jev requires `JEV_API_KEY`. Laya requires its local Jev-compatible service at the configured URL.
The report includes the dataset SHA-256, per-case evidence and selection, coverage Brier score,
acceptable/preferred selection rates, usage returned by the backend, and latency summaries.

## v2 controlled closed-loop evaluation

`v2_controlled.json` covers adequate, candidate-deletion, distractor, duplicate, unavailable-tool,
constraint-failure, NOTA, insufficient-information, expansion-recovery, and native multimodal
conditions. It is a deterministic acceptance fixture, not a general ability benchmark.

```bash
python scripts/evaluate_v2.py --output results/v2_controlled.json
```

The report persists per-round coverage and selection evidence, candidate quality, typed feedback,
controller action, feedback bandwidth, component latency, and compute/budget accounting.

Run the matched live Jev adequate-versus-deleted comparison and persist the normalized result:

```bash
python scripts/evaluate_v2_jev_deletion.py --output results/v2_jev_deletion.json
```

This requires `JEV_API_KEY`; the input set is fixed in `v2_jev_candidate_deletion.json`.

## v4 controlled calibration and adaptive compute

`v4_evaluation.json` is the complete deterministic report produced by `scripts/evaluate_v4.py`.
It contains fixed train/validation/test metadata, calibration artifacts and held-out metrics,
verifier correlations, NOTA analysis, named feedback baselines, fixed/adaptive compute results,
conformal routing, and separate calibration/candidate-quality/feedback ablations.

`v4_risk_latency_token.csv` is the plot-ready projection of the corresponding curve, and the SVG
is the dependency-free rendering recreated by the same script. These files are controlled
fixtures, not live-model performance evidence.
