# Changelog

## Unreleased

- Implemented v4 CPU-only calibration records, stable dataset hashing, Platt scaling, learned
  logistic coverage estimation, and versioned calibration artifacts with held-out metrics.
- Added controlled candidate-set corruptions and learned candidate-quality features, NOTA-aware
  analysis, conformal routing comparison, and same-backbone/independent-verifier correlation.
- Added a smoothed typed-feedback recovery policy, cost-aware expansion controller, calibrated
  fast/slow router, and risk-latency-token aggregation.
- Added the reproducible controlled v4 evaluator with typed/binary/long-form feedback baselines,
  fixed/adaptive compute comparison, separate ablations, JSON evidence, and plot-ready CSV output.

- Began v3 with a project-owned `NativeDLMDecisionBackend`, deterministic coverage/selection
  canvases, strict label/logit validation, normalized probabilities, and injectable same-process
  runtime support.
- Added a shared-process LLaDA-V masked-label endpoint and verified real text and native-image
  coverage/selection reads on the complete local checkpoint.
- Added bounded content-addressed vision-feature reuse with cache diagnostics and retained matched
  before/after latency evidence.
- Added opt-in batched coverage/selection reads and recorded the matched CPU regression, retaining
  cached sequential reads as the default.
- Added a first-class local `LladaGenerator` and configuration kind.
- Centralized bounded structured-output regeneration across OpenAI-compatible generators with
  aggregate repair, token-usage, and latency telemetry.

- Replaced the abandoned external GPU-server plan with two supported generator paths: hosted
  Mercury for fast text decisions and the proven local DiffusionGemma runtime for local/native-image
  decisions.
- Extended compact generation output with optional tool and constraint metadata and added
  deterministic detection for explicit `do not` / `must not` constraints in string-only output.
- Implemented v2 native multimodal image references and OpenAI-compatible generator/Djev
  transport with explicit capability negotiation, media validation, and bounded payloads.
- Added deterministic candidate-quality checks, budget-aware closed-loop routing, typed
  escalation results, and complete per-round latency/compute/feedback telemetry.
- Added the 11-condition v2 controlled corruption/recovery matrix and reproducible report runner.

- Implemented the v1 OpenAI-compatible DiffusionGemma generator client with bounded repair,
  typed-feedback expansion context, timeouts, and generation telemetry.
- Added Jev Cloud, local Djev, and cross-encoder reference backends with normalized evidence,
  capability declarations, fixture tests, and independent coverage semantics.
- Corrected the hosted Jev default to the official `https://api.typesafe.ai` endpoint and
  added a separately identified local Laya backend and smoke profile.
- Added configuration factories, runtime smoke tooling, and text-only real-service examples.
- Completed a consumer-PC CPU trial with DiffusionGemma Q4_K_M, hosted Jev, and local Laya;
  recorded latency/memory measurements and the current strict-JSON output limitation.

- Renamed the project and Python package to **DiCoJev** / `dicojev`.
- Reframed the research thesis around diffusion-generated candidate sets, explicit candidate-set coverage, and Jev-style compact decision reads.
- Promoted typed low-bandwidth feedback to a first-class project protocol.
- Added `FeedbackCode`, `FeedbackSignal`, `FeedbackBundle`, `FeedbackCompiler`, and `LoopContext` to the stable architecture.
- Updated v0-v5 release scope to include feedback-loop implementation and evaluation.
- Added a dedicated real-DLM runtime planning document while preserving CPU-only v0 tests.
