# v4 Evaluation and Release Decision

## Evidence boundary

The v4 release adds the mechanisms and reproducible evaluation path required by the roadmap. Its
committed benchmark is a deterministic, CPU-only controlled fixture with 90 candidate sets split
50/20/20 for train/validation/test. It is not a claim about DiffusionGemma, LLaDA, Mercury, Jev,
or Djev performance. Controlled latency and token values are accounting inputs rather than
wall-clock measurements.

## Calibration and learned coverage

On the held-out 20-case test split, the deliberately overconfident raw coverage score had Brier
score 0.4539 and expected calibration error (ECE) 0.5307. Platt scaling reduced Brier score to
0.1182 and ECE to 0.2395. The independently fitted feature-based coverage verifier reached Brier
score 0.1419 and ECE 0.1615. Raw and calibrated scores remain separate fields.

The same-backbone raw score and independent-verifier prediction had Pearson correlation 0.6604.
Their correlations with adequacy labels were 0.6114 and 0.6669 respectively. This is evidence that
the controlled verifier is related but not identical; it does not establish independence for a
real model stack.

NOTA identified 3 of 13 inadequate held-out sets (23.1%). That weak fixture result is retained
rather than hidden: NOTA alone is not an adequate coverage detector in this benchmark.

Calibration is operational rather than report-only: versioned artifacts can reconstruct their
Platt or logistic estimator, `CalibratedDecisionBackend` preserves raw evidence while populating
separate calibrated fields, and the cost-aware controller can route on calibrated coverage and
selection while including typed-feedback token cost in expansion utility.

Artifact schema v2 records the explicit training split and count, a hash of training case IDs,
fitting hyperparameters, and a SHA-256 revision of the evaluator/calibration source. Controlled
artifact time is fixed to the dataset release date, making the complete JSON report byte-for-byte
reproducible rather than only numerically reproducible.

## Feedback and adaptive compute

The five-case feedback fixture produced:

| Policy | Recovery | Mean feedback tokens | Recoveries / 100 tokens |
|---|---:|---:|---:|
| Typed feedback | 0.80 | 12 | 6.67 |
| Binary retry | 0.40 | 4 | 10.00 |
| Long-form feedback | 0.80 | 80 | 1.00 |

Typed feedback matches long-form recovery at much lower bandwidth, but binary retry is more token
efficient on this small controlled set. v4 therefore does not claim universal typed-feedback
dominance.

The fixed/adaptive accounting comparison is:

| Policy | Risk | Mean latency (ms) | Mean tokens | Expansion rate |
|---|---:|---:|---:|---:|
| Fixed one round | 0.65 | 28.0 | 18.0 | 0.00 |
| Adaptive | 0.50 | 42.7 | 22.2 | 0.35 |
| Fixed two rounds | 0.35 | 70.0 | 30.0 | 1.00 |

Adaptive routing occupies the intended middle point: lower controlled risk than one round, with
less cost than always expanding. It does not dominate the fixed two-round policy on risk. That is
the expected tradeoff, not evidence that coverage awareness is ineffective.

## Other acceptance evidence

- Candidate quality features separately represent count, uniqueness, tool coverage, and constraint
  compliance.
- The corruption generator creates adequate, acceptable-deleted, duplicate-added, and
  distractor-added cases without changing the canonical decision schema.
- A smoothed typed-feedback recovery model preserves the existing feedback vocabulary.
- The cost-aware controller can convert low-value `EXPAND` decisions into fail-closed `ABSTAIN`.
- The fast/slow router honors calibrated zero values and fails closed when evidence is missing.
- A conformal threshold triggered 9 rather than 20 extra rounds in the controlled comparison.
- Calibration, candidate-quality-only, and feedback-removed ablations are persisted separately.
- Reliability bins are persisted for raw, calibrated, and independent-verifier scores.
- `benchmarks/v4_risk_latency_token.csv` and its SVG rendering are recreated from the run artifact.

## Live and native companion evidence

- `benchmarks/v4_jev_live.json` records five live hosted-Jev 1.13.0 cases: acceptable selection was
  100%, preferred selection was 80%, and mean raw coverage was 0.966.
- `benchmarks/v4_jev_deletion_live.json` records a matched deletion pair: coverage fell from 0.96
  to 0.38 when all acceptable actions were removed, and selection changed from `A` to NOTA.
- `benchmarks/v4_native_repeatability.json` records five fixed-configuration local LLaDA reads with
  zero logit span and unchanged selection.
- `benchmarks/v4_runtime_audit.json` records that both local checkpoints are present, hosted Jev and
  Mercury credentials are configured, and the abandoned local services were offline during audit.

The larger 20-condition hosted-Jev calibration runner is implemented as
`scripts/evaluate_v4_live_jev.py`. Its inputs are human-auditable variants of the five repository
fixtures. The resulting artifact is only created when external-dataset submission is explicitly
authorized; controlled v4 tests never require it.

## Decision

The v4 software and controlled acceptance gates are implemented. The results establish that the
pipeline can fit, version, evaluate, and use calibrated coverage and adaptive policies without
GPU/network dependencies. They do not establish real-world effectiveness; that requires a larger
held-out task set with live backend scores and measured wall-clock cost, which belongs in the v5
research release evaluation.
