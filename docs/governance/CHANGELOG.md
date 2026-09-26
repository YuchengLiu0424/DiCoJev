# Changelog

## Unreleased

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
