# Changelog

## Unreleased

### 1.2.0

- Added a restricted deterministic arithmetic route so simple calculations bypass candidate
  generation and return direct answers without requiring a model service.
- Separated component outages from epistemic escalation in the GUI: model failures now display as
  `UNAVAILABLE`, while `ESCALATE` remains a decision-loop outcome.
- Made context-only drafting fail soft when the configured DLM is offline, with a clearly labeled
  low-confidence local draft that still requires review.
- Moved the active-chat transcript to the rightmost column with right-aligned structured requests
  and left-aligned adequacy, coverage, option-score, and choice results.
- Reworked every floating field hint into one description line followed by one example line.
- Added Workspace and Settings scenes inside one native window, with DPAPI-protected model keys.
- Added a model registry and independent language/decision model assignments for each project chat.
- Defaulted new chats to local DiffusionGemma and local Laya; retained unified LLaDA as a research configuration.
- Added rounded, padded project/chat navigation with right-click rename and deletion.
- Removed desktop dependence
  on environment variables.
- Added provider-reported token accounting grouped by model and chat.
- Added numbered default chat names, rename, confirmed deletion, and an active-chat interaction
  history column.
- Added persistent projects, a project file browser, and a path-confined `ProjectWorkspace` API
  that is read-only unless write access is explicitly granted.
- Kept arbitrary shell and desktop control disabled pending a separate capability/consent design.

### 1.1.0

- Added context-only DLM intent drafting with explicit review of inferred goals, constraints,
  assumptions, and proposed tools.
- Added private local SQLite profiles, multiple chats, bounded recent-history recall, a reserved
  explicit-memory schema, and an in-app data-folder shortcut.
- Added a Windows desktop-shortcut installer for the native Decision Studio.
- Added a native dark desktop Decision Studio and `dicojev-gui` entry point using the direct
  in-process Python runtime rather than the FastAPI surface.
- Added Windows per-monitor-v2 DPI rendering, monitor-calibrated Tk scaling, example placeholders,
  and a multi-resolution diffusion-to-structured-decision application mark.
- Added `DirectClient` for typed embedding in other Python programs without public HTTP transport.
- Added bounded local attachment preprocessing for images, text/data/code files, and optional
  PDF, DOCX, speech transcription, and sampled video frames/audio.

- Implemented the v5 unified LLaDA runtime facade so generation and native structured reads share
  one configured model-server process and diagnostics surface.
- Added the stable optional `POST /v1/decide` API, explicit allowlisted tool boundary, and
  action-result/environment-transition traces.
- Added the v5 offline end-to-end benchmark, full-action/multimodal coverage, p50/p95 latency,
  Python memory, feedback-token, risk-latency-token, and cache-equivalence reporting.
- Added a zero-service executable agent demo and promoted package metadata/configuration to
  `v5` / `1.0.0`.
- Added the installable `dicojev-api` entry point, made the evidence-supported threshold controller
  the runnable default, and documented adaptive compute as an explicit fitted-policy experiment.
- Completed the final documentation audit with a model-free quickstart, current LLaDA-V serving
  path, evidence/limitation table, adjacent-framework comparison, and holistic project review.

- Implemented v4 CPU-only calibration records, stable dataset hashing, Platt scaling, learned
  logistic coverage estimation, and versioned calibration artifacts with held-out metrics.
- Added controlled candidate-set corruptions and learned candidate-quality features, NOTA-aware
  analysis, conformal routing comparison, and same-backbone/independent-verifier correlation.
- Added a smoothed typed-feedback recovery policy, cost-aware expansion controller, calibrated
  fast/slow router, and risk-latency-token aggregation.
- Added the reproducible controlled v4 evaluator with typed/binary/long-form feedback baselines,
  fixed/adaptive compute comparison, separate ablations, JSON evidence, and plot-ready CSV output.
- Made calibration artifacts reloadable, added a raw-preserving calibrated backend wrapper, and
  routed cost-aware expansion using calibrated evidence plus feedback-token cost.
- Upgraded calibration artifact provenance with training-split identity, fit hyperparameters,
  source revision, and deterministic controlled timestamps; the full v4 JSON now reproduces
  byte-for-byte.
- Closed the v3 tolerance gate with five identical fixed-configuration local LLaDA reads and added
  hosted Jev 1.13.0 to the exact matched Native/CrossEncoder comparison after the local Djev GPU
  deployment was explicitly abandoned.
- Replaced constructed v4 feedback and adaptive-compute outcomes with matched live Mercury/Jev
  loop executions, retaining the negative typed-feedback and adaptive-policy results.
- Added task-disjoint live Jev calibration and a matched local-LLaDA/hosted-Jev verifier
  correlation study.

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
