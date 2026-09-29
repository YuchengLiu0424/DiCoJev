# Version Control and Release Plan

This is the single authoritative source for planned versions, branch sequencing, milestone scope, and acceptance gates. The root README must not duplicate this roadmap.

## 1. Git policy

Each milestone is developed from the latest `main` using one integration branch:

```text
version/v0
version/v1
version/v2
version/v3
version/v4
version/v5
```

Normal flow:

```text
main -> version/vN -> implementation/tests/docs -> PR -> main -> tag vN
```

Do not start `version/vN+1` from an unmerged predecessor.

## 2. Scope freeze

The intended program through v5 is declared below. New research capabilities discovered during implementation belong in a v6+ ADR unless they correct a bug/safety/interface defect or are necessary to realize an already declared capability.

## 3. Cross-version invariants

- architecture = DLM CandidateGenerator + DecisionHarness + pluggable DecisionBackend + RiskController + typed FeedbackCompiler/LoopContext;
- Jev and Djev are optional reference backends;
- DLM generation followed by Djev is a two-diffusion-stage baseline;
- `q_cov`, `q_sel`, and candidate quality are distinct;
- raw and calibrated scores are distinct;
- NOTA is backend evidence, not a controller action;
- feedback codes are typed project-level signals, not free-form chain-of-thought;
- feedback is not a fourth Jev question component;
- images remain first-class for native multimodal evaluation;
- unit tests require no GPU/network/API keys;
- provider wire formats do not become canonical `DecisionSpec` fields;
- infrastructure/evidence failures fail closed.

Detailed semantics are owned by `docs/design/`.

---

# v0 — Protocol, Deterministic Harness, and Typed Feedback Loop

**Package target:** `0.1.0`  
**Branch:** `version/v0`  
**Tag:** `v0`

## Scope

Create an installable CPU-only reference implementation of:

- public request/response schemas;
- `DecisionSpec`, candidates, budgets, traces;
- `CandidateGenerator`, `DecisionBackend`, `RiskController`, `EscalationTarget` protocols;
- deterministic fake generator and mock backend;
- JSON extraction/bounded repair;
- candidate normalize/dedupe/stable-ID registry;
- tool/constraint validation stubs;
- synthetic NOTA injection;
- Jev-compatible coverage + selection compiler;
- normalized backend result;
- `FeedbackCode`, `FeedbackSignal`, `FeedbackBundle`, `LoopContext`;
- deterministic `FeedbackCompiler`;
- threshold controller capable of all four meta-actions and typed feedback;
- at least one fully offline EXPAND -> feedback -> regenerate -> reevaluate loop;
- telemetry including feedback code and payload-size fields.

## Acceptance gate

- package imports CPU-only;
- `pytest` passes without GPU/network/API keys;
- ACT/EXPAND/ABSTAIN/ESCALATE all occur in deterministic fixtures;
- exact Jev compilation has snapshot tests;
- invalid/empty candidate cases fail closed;
- provider fields do not leak into `DecisionSpec`;
- `q_cov` is never silently derived from `q_sel`;
- raw/calibrated nullability follows decision semantics;
- feedback vocabulary validates strictly;
- `FeedbackCompiler` has deterministic snapshot tests;
- offline example demonstrates at least one typed-feedback expansion round and stable candidate IDs.

---

# v1 — Real DLM Generation and Reference Backends

**Package target:** `0.2.0`  
**Branch:** `version/v1`  
**Tag:** `v1`

## Scope

- local `DiffusionGemmaGenerator` using `google/diffusiongemma-26B-A4B-it` by default;
- documented fresh-machine model-serving path, model cache, health check, and smoke test;
- configurable local generator client with timeout/cancellation/telemetry;
- generator consumption of typed `LoopContext` / compiled feedback;
- robust `DecisionSpec` generation;
- `JevCloudBackend`;
- `DjevLocalBackend`;
- `LayaLocalBackend` as an open-weight Jev-compatible comparison;
- `CrossEncoderDecisionBackend`;
- backend capability negotiation;
- config-only backend selection;
- text-only real-model end-to-end examples;
- latency decomposition including feedback compilation and repeated generation.

## Acceptance gate

- documented local DLM serving path reaches a successful candidate-generation smoke test;
- real generator can consume an expansion `LoopContext` without paraphrasing all prior candidates in controlled fixtures;
- same normalized set can reach all compatible backends;
- hosted Jev and local Laya can evaluate the same persisted candidate set;
- Jev credentials remain optional/environment-only;
- Djev is accessed through a local adapter, not vendored into core;
- two-DLM-stage topology is measurable;
- cross-encoder coverage method remains separate from ranking confidence;
- mock backend remains default unit-test dependency.

---

# v2 — Native Multimodal Coverage-Aware Closed Loop

**Package target:** `0.3.0`  
**Branch:** `version/v2`  
**Tag:** `v2`

## Scope

- first-class image references/bytes/data URLs in `MultimodalState`;
- native image transport to supported generator/backend paths;
- modality capability checks;
- multi-round EXPAND loop with stable IDs;
- explicit candidate, expansion, latency, and compute budgets;
- candidate-quality flags;
- typed feedback generation for candidate omission, redundancy, tool mismatch, constraint failure, ambiguity, and insufficient information;
- multimodal/candidate-deletion controlled fixtures;
- per-round trace including feedback bandwidth.

## Acceptance gate

- text+image state reaches the DLM generator natively;
- at least one decision path consumes equivalent multimodal evidence without silent caption-only substitution;
- removing acceptable candidates measurably degrades coverage evidence;
- coverage-aware routing avoids forced ACT on inadequate sets;
- typed `MISSING_ACTION` feedback recovers an omitted acceptable action on controlled tasks;
- at least two other feedback codes change regeneration behavior in the intended direction;
- all four controller actions occur in integration tests;
- per-round/total latency and feedback tokens/bytes are reported.

---

# v3 — Project-Owned Native Diffusion Structured Read

**Package target:** `0.4.0`  
**Branch:** `version/v3`  
**Tag:** `v3`

## Scope

- `NativeDLMDecisionBackend` behind the existing interface;
- deterministic read template/canvas construction;
- compact candidate-label validation;
- binary coverage read;
- categorical selection read;
- probability/logit extraction and normalization;
- read diagnostics;
- same-process/model-weight use where runtime permits;
- comparison against DjevLocal and CrossEncoder;
- existing feedback/controller loop remains unchanged above the backend abstraction.

## Acceptance gate

- normalized native backend result without a Djev server;
- reproducible coverage/selection reads within documented tolerance;
- token/label failures are caught before unsafe reads;
- backend switching requires no public API change;
- comparison includes CrossEncoder plus either DjevLocal or hosted Jev under matched candidate
  sets; hosted Jev is the required independent reference when the local GPU deployment is
  explicitly unavailable;
- typed feedback behavior remains backend-neutral.

---

# v4 — Calibration, Learned Coverage, Feedback Policy, and Adaptive Compute

**Package target:** `0.5.0`  
**Branch:** `version/v4`  
**Tag:** `v4`

## Scope

- calibration dataset format and calibrators;
- calibration metadata/versioning;
- learned coverage estimator(s);
- independent/decorrelated coverage-verifier experiment;
- learned candidate-quality features;
- controlled candidate-set corruption benchmark generator;
- NOTA-aware calibration analysis;
- conformal/repeated-generation comparison where appropriate;
- learned or calibrated feedback-code policy while preserving typed protocol;
- typed feedback vs binary retry vs long-form feedback comparison;
- cost-aware controller using risk + latency/compute/token budget;
- fast/slow routing experiments;
- reliability, risk-latency, and risk-latency-token curves.

## Acceptance gate

- raw and calibrated values are reproducible and separate;
- held-out coverage calibration metrics are reported;
- coverage estimator is evaluated against candidate-set adequacy labels;
- same-backbone vs independent-verifier correlation is measured;
- typed feedback recovery/token efficiency is compared against named baselines;
- adaptive compute is compared with fixed budgets;
- candidate quality, coverage, and feedback ablations are reported separately;
- evaluation scripts recreate core research tables/plots from run artifacts.

---

# v5 — Unified Fast Multimodal Agent Runtime and Research Release

**Package target:** `1.0.0`  
**Branch:** `version/v5`  
**Tag:** `v5`

## Scope

- one project-controlled multimodal DLM runtime supporting generation and structured read;
- shared model weights/process and safe preprocessing/state reuse where valid;
- stable `/v1/decide`-style project API;
- tool/environment execution boundary;
- full typed feedback loop exposed in traces;
- action-result/environment-transition trace;
- full text + multimodal benchmark suite;
- all reference backends retained for reproduction;
- end-to-end p50/p95 latency, GPU memory, feedback token, and risk-latency-token evaluation;
- reproducible configs and release documentation.

## Acceptance gate

- one runtime executes both candidate generation and project-owned structured read;
- primary local path requires no Jev/Djev dependency;
- shared-runtime optimizations have before/after measurements;
- safety/correctness equivalence is checked for reused state/cache;
- public API supports ACT/EXPAND/ABSTAIN/ESCALATE plus typed feedback traces;
- full benchmark reproduces main research claims;
- clean installation and local demo succeed from a fresh environment;
- documentation passes the ownership-map consistency check.

## 4. Release PR checklist

Every milestone PR confirms:

```text
[ ] scope matches this document
[ ] matching agent task completed
[ ] offline unit tests pass
[ ] relevant integration tests pass or are hardware-gated
[ ] authoritative docs updated only when contracts changed
[ ] no duplicated normative definitions introduced
[ ] configs/examples match behavior
[ ] changelog updated
[ ] no secrets/model weights/private raw data
[ ] no undeclared later-milestone scope
```

## 5. v6+ rule

New research directions outside this plan should be recorded as ADR/backlog entries with problem, motivation, affected interfaces, and required experiments. Tagged milestone meaning is never retroactively changed.
