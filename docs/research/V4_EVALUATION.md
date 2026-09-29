# v4 Evaluation and Release Decision

## Evidence boundary

The v4 release combines a deterministic 90-record calibration fixture with explicitly labeled live
Mercury generation, hosted-Jev verification, and local-LLaDA native-read evidence. The live studies
contain only five base tasks (and six conditions for verifier correlation), so they close the
mechanical acceptance gates without supporting broad model-performance claims.

## Calibration and learned coverage

On the held-out 20-case test split, the deliberately overconfident raw coverage score had Brier
score 0.4539 and expected calibration error (ECE) 0.5307. Platt scaling reduced Brier score to
0.1182 and ECE to 0.2395. The independently fitted feature-based coverage verifier reached Brier
score 0.1419 and ECE 0.1615. Raw and calibrated scores remain separate fields.

The same-backbone raw score and independent-verifier prediction had Pearson correlation 0.6604.
Their correlations with adequacy labels were 0.6114 and 0.6669 respectively. This is evidence that
the controlled verifier is related but not identical; it does not establish independence for a
real model stack.

The live task-disjoint hosted-Jev study contains 20 corruption conditions split 12/4/4 by base
task. On the four-condition held-out task, Platt calibration reduced Brier score from 0.0027 to
0.00000432. Mean coverage was 0.966 for adequate sets and 0.158 after acceptable-action deletion;
NOTA selected every deleted set. The test set is only one base task, so this is pipeline evidence,
not a stable population estimate.

On six identical adequate/deleted sets, local native LLaDA and hosted Jev coverage had Pearson
correlation 0.487. Jev correlated with adequacy at 0.946, while native LLaDA correlated at 0.364.
The real verifiers are partly decorrelated, but the current native read is substantially weaker.

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

Five matched loops used the same deficient first-round candidates, real Mercury regeneration, the
unchanged controller, and hosted-Jev reevaluation:

| Policy | Recovery | Mean feedback tokens | Recoveries / 100 tokens |
|---|---:|---:|---:|
| Typed feedback | 0.60 | 24 | 2.50 |
| Binary retry | 0.60 | 8 | 7.50 |
| Long-form feedback | 0.80 | 53 | 1.51 |

Typed feedback did not outperform either baseline: it matched binary retry's recovery at three
times the feedback tokens, while long-form recovered one additional case. This negative result is
retained and supersedes the earlier constructed comparison.

The fixed/adaptive table also comes from executed loops:

| Policy | Risk | Mean latency (ms) | Mean tokens | Expansion rate |
|---|---:|---:|---:|---:|
| Fixed one round | 1.00 | 1583.6 | 0 | 0.00 |
| Adaptive | 1.00 | 1337.7 | 0 | 0.00 |
| Fixed two rounds | 0.40 | 4971.8 | 24 | 1.00 |

The learned recovery probability was 0.40, below the configured 0.50 expansion cost, so adaptive
routing declined every expansion. It saved compute but did not improve risk. Coverage-aware
routing remains safe and operational, but this policy/data combination is ineffective.

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
- `benchmarks/v4_jev_calibration_live.json`, `v4_feedback_policies_live.json`, and
  `v4_verifier_correlation_live.json` contain the authorized live evaluation records described
  above, including full per-round traces and provider usage without credentials.

## Decision

The v4 software and research-mechanics gates are closed. Calibration works strongly on this small
Jev study, while typed feedback, adaptive expansion, and native LLaDA coverage do not demonstrate
superiority. v4 is therefore a complete, reproducible negative/ mixed result rather than a claim
that coverage awareness is already effective. Larger tasks, multimodal end-to-end runs, and policy
improvement remain v5 work.
