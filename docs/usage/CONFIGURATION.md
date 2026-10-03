# Configuration Reference

This file owns repository configuration-key meanings. Config files instantiate design choices; they do not redefine semantics.

## `project`

```yaml
project:
  name: dicojev
  environment: local
```

## `model`

```yaml
model:
  generator_kind: diffusiongemma
  generator_model: dicojev-diffusiongemma
  deployment: separate_models
  base_url: http://127.0.0.1:11434
  timeout_seconds: 600
  max_candidates: 8
```

`generator_kind` may be `fake`, `llada`, `mercury`, `diffusiongemma`, or `openai_compatible`.
The desktop defaults to separate local DiffusionGemma and Laya services. Unified LLaDA remains
available through the historical research configuration. The desktop stores a distinct
API key for the active model through **Settings**; headless legacy construction may still pass a
key explicitly or use `INCEPTION_API_KEY`. Mercury defaults to
`https://api.inceptionlabs.ai/v1` and `mercury-2.5` and declares text-only capability.
DiffusionGemma uses the configured local OpenAI-compatible endpoint and declares native image
capability.

## `decision_backend`

```yaml
decision_backend:
  kind: laya_local
  base_url: http://127.0.0.1:8000
  model: english
  timeout_seconds: 600
```

## `controller`

```yaml
controller:
  policy: threshold  # safe v5 default
  min_coverage: 0.75
  min_selection_confidence: 0.70
  max_expansions: 2
  max_total_candidates: 16
  allow_abstain: true
  allow_escalate: true
```

Thresholds are experimental defaults, not universal guarantees.

Set `supports_native_multimodal: true` for `djev_local` only when that deployed service accepts
the v2 `state.images` wire entries. The default is false and image requests fail closed.

## `feedback`

```yaml
feedback:
  compiler: deterministic_templates
  max_signals_per_round: 3
  default_expand_count: 3
  allow_freeform_reasoning: false
  record_serialized_size: true
```

Canonical code meanings live only in `docs/design/FEEDBACK_PROTOCOL.md`.

## `telemetry`

```yaml
telemetry:
  enabled: true
  log_raw_text: false
  log_images: false
  preserve_raw_scores: true
  preserve_calibrated_scores: true
  log_feedback_codes: true
  log_feedback_size: true
```

## Secrets

Hosted provider credentials such as `JEV_API_KEY` belong only in environment variables/secrets.

## Profiles

Deployment profiles under `configs/` may select mock, Djev, cross-encoder, or native DLM paths. Version snapshots under `configs/versions/` are governed by `VERSION_CONTROL.md` and are not semantic sources of truth.

## v5 unified runtime

The v5 primary configuration uses `deployment: unified_local_runtime`, `generator_kind: llada`,
and the native backend through one `UnifiedLladaRuntime` instance. The shipped policy is
`threshold`, matching the evidence boundary and making the default config directly constructible.
If `controller.policy` is changed to `adaptive_compute`, `create_agent_runtime()` requires a fitted
`FeedbackRecoveryPolicy`; an untrained policy can never silently control expansion.

The API is enabled with `api.endpoint: /v1/decide`. Tool execution is never configured as an
arbitrary command string: callers inject an `AllowlistedToolExecutor` whose named handlers receive
the selected candidate's bounded `arguments_hint` and return a result plus updated state.
