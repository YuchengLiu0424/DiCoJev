# Configuration Reference

This file owns the meaning of repository configuration keys. Configuration files instantiate design choices; they do not redefine system semantics.

## 1. `project`

```yaml
project:
  name: diffusion-decision
  environment: local
```

Metadata only. Release metadata may be maintained by governance tooling but does not change decision semantics.

## 2. `model`

```yaml
model:
  generator_kind: fake
  generator_model: google/diffusiongemma-26B-A4B-it
  deployment: local
  base_url: http://127.0.0.1:8000
  timeout_seconds: 60
  max_candidates: 8
```

- `generator_kind`: implementation selected for candidate generation.
- `generator_model`: model identifier.
- `deployment`: local/remote implementation hint.
- `base_url`: service endpoint when generation is served out of process.
- `timeout_seconds`: hard request timeout.
- `max_candidates`: per-generation candidate limit before controller-level total budgets.

## 3. `decision_backend`

```yaml
decision_backend:
  kind: mock
  base_url: null
  model: null
  timeout_seconds: 30
```

Supported backend names are implementation registrations, not architecture constants. Provider credentials belong in environment variables/secrets.

## 4. `controller`

```yaml
controller:
  policy: threshold
  min_coverage: 0.75
  min_selection_confidence: 0.70
  max_expansions: 2
  max_total_candidates: 16
  allow_abstain: true
  allow_escalate: true
```

Threshold values are experimental defaults, not universal safety guarantees. Their semantic inputs are defined only in `docs/design/DECISION_SEMANTICS.md`.

## 5. `telemetry`

```yaml
telemetry:
  enabled: true
  log_raw_text: false
  log_images: false
  preserve_raw_scores: true
  preserve_calibrated_scores: true
```

Raw images should remain disabled by default. Raw and calibrated model scores should be preserved as distinct values.

## 6. Environment secrets

Examples:

```text
JEV_API_KEY
```

Secrets must never appear in committed YAML, tests, examples, or telemetry fixtures.

## 7. Profile convention

Repository profiles under `configs/` should be named by deployment intent, for example:

```text
default.yaml
local_djev.yaml
local_cross_encoder.yaml
local_native_dlm.yaml
```

Profiles under `configs/versions/` are development/reproducibility snapshots and are governed by `docs/governance/VERSION_CONTROL.md`; they are not the conceptual source of truth for system semantics.
