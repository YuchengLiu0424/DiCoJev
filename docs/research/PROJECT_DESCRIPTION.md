# Project Description and Research Charter

## 1. Working title

**Diffusion Decision: Coverage-Aware Multimodal Decision Making over Self-Generated Action Sets**

This document is the research starting point for the project and is intentionally more complete than the GitHub README. It should be suitable for evolving into the introduction, problem formulation, motivation, and contribution sections of a paper.

It does **not** define software release sequencing, branch names, or coding-agent tasks.

## 2. Research thesis

Most fast decision systems become reliable only after somebody has already specified the decision space: labels, candidate actions, answer options, scoring criteria, or tool calls. Open-world agents do not receive that guarantee. They often have to infer what decisions are available before choosing among them.

This creates a fundamental mismatch between **selection confidence** and **decision completeness**.

Suppose a candidate generator proposes:

```text
C = {a1, a2, a3}
```

and a selector reports:

```text
P(a1 | x, C) = 0.95
```

The value can be meaningful as a closed-set preference while still being dangerously misleading for the original task if every candidate is bad or the genuinely useful action is missing from `C`.

Diffusion Decision studies the following question:

> **Can a fast multimodal diffusion model construct its own candidate action set, estimate whether that set is adequate, make a calibrated conditional choice when it is adequate, and spend additional computation only when the generated decision space is insufficient?**

The target is not generic text generation. The target is a **fast System-1-like decision layer** for agents.

## 3. Concrete problem being solved

The system receives a state containing some combination of:

- text observation;
- image/screenshot observation;
- structured environment state;
- task goal;
- available tools or executable action primitives;
- constraints and permissions;
- bounded interaction history;
- compute/risk budget.

It must produce a useful next decision without requiring the caller to enumerate every possible action in advance.

The difficulty is split into four problems:

### 3.1 Candidate construction

The system has to produce a compact set of plausible next actions from an open or very large semantic action space.

### 3.2 Candidate-set adequacy

The system must estimate whether the current set contains at least one acceptable next action. This is different from asking which candidate looks best relative to the others.

### 3.3 Conditional selection

If the set is adequate, the system needs a fast structured read that selects among the candidate actions and exposes useful uncertainty.

### 3.4 Computation control

If the set is not adequate—or if the best candidate remains too uncertain—the system should be able to generate more candidates, abstain, or escalate to a slower planner instead of forcing an action.

## 4. System formulation

Let:

- `x` be the multimodal observation/state;
- `g` be the task goal;
- `T` be available tools and constraints;
- `C_t = {a_1, ..., a_K}` be the candidate set after generation round `t`;
- `A*(x,g,T)` be the set of acceptable next actions;
- `a_hat` be the selected action.

The generator constructs:

```text
C_t ~ G_theta(x, g, T, history)
```

The decision system estimates at least two distinct quantities:

```text
q_cov = P(C_t intersects A* | x, g, T, C_t)
```

and

```text
q_sel = confidence / probability-like evidence that a_hat is acceptable
        conditional on the supplied candidate set being adequate.
```

The controller then chooses a meta-action:

```text
u_t in {ACT, EXPAND(k), ABSTAIN, ESCALATE(target)}
```

A useful research objective is not accuracy alone, but a risk-cost trade-off such as:

```text
expected task loss
+ lambda_latency * latency
+ lambda_compute * compute cost
+ lambda_bad_action * unsafe/incorrect execution cost
```

The exact calibration and decision-theoretic interpretation of model scores must be established empirically rather than assumed.

## 5. Why a DLM instead of an LLM + decision model

An autoregressive LLM plus Jev-like selector is a valid baseline and may be strong. It is not the intended architectural thesis.

The DLM choice is motivated by four properties:

1. **Latency-oriented generation.** Diffusion-style generation can refine blocks of tokens in parallel rather than strictly decoding token by token.
2. **Multimodal local model availability.** DiffusionGemma is available as an image-text-to-text model and can be served locally.
3. **Structured-read compatibility.** Djev demonstrates that a diffusion model can be used with seeded/pinned canvases and read-only answer slots to obtain Jev-style probability-backed decisions.
4. **Potential runtime unification.** A single project-controlled DLM runtime may eventually support both open candidate generation and compact structured reads, avoiding a permanent architecture consisting of two unrelated model families.

This is a research hypothesis, not a guaranteed advantage. A conventional encoder/ranker may be faster or better calibrated for some workloads and is therefore an essential baseline.

## 6. Why the harness is a first-class contribution

The project does not ask the DLM to directly emit final provider-specific Jev JSON. A dedicated harness converts open generation into a stable decision problem.

The harness owns:

```text
raw DLM generation
 -> JSON extraction / bounded repair
 -> DecisionSpec validation
 -> candidate normalization
 -> semantic deduplication
 -> tool/constraint checks
 -> stable candidate IDs
 -> synthetic NOTA insertion
 -> backend-specific compilation
 -> normalized decision result
```

This creates a clean separation between:

- **semantic actions**, which may be arbitrary text/structured tool calls; and
- **decision labels**, which can remain compact single-token identifiers such as `A`, `B`, `C`, and `N`.

The distinction matters for Djev-style structured reads where answer labels may be constrained by tokenization.

## 7. Application scenarios

### 7.1 Computer-use and GUI agents

A screenshot, task goal, available controls, and interaction history can produce a small action set such as:

```text
A: open the recipient field
B: send the message
C: save as draft
```

If the correct action is actually “attach the edited document” and it is absent, a normal ranker may still confidently choose among A/B/C. Coverage-aware routing can instead request more candidates or escalate.

This domain is particularly attractive because multimodal perception, fast next-action selection, and measurable environment success all matter.

### 7.2 Tool-using software agents

A coding/operations agent can generate candidate tool calls, validate them against available tools and permissions, then use structured decision reads before execution.

Candidate-set coverage can detect situations where the generator only considered diagnostic actions but missed the required repair action, or generated several variants of the same command while omitting a qualitatively different strategy.

### 7.3 Customer-support routing and workflow automation

The system can construct context-specific actions instead of forcing every workflow into a globally fixed taxonomy. Examples include routing, requesting missing information, escalating, offering a resolution, or taking no action.

The main value here is not merely classifying into a department but deciding whether the currently proposed operational actions are sufficient.

### 7.4 Embodied or simulated agents

In environments with many possible action compositions, the DLM can propose a compact semantic action set and the decision layer can control whether to execute or expand it.

This is useful where the low-level action space is large but the number of sensible high-level actions at a given state is small.

### 7.5 High-stakes domains as research/evaluation only

Medical triage, financial risk, and other high-stakes domains illustrate the conceptual value of `ABSTAIN` and `ESCALATE`, but the project should not present an experimental model as an autonomous high-stakes decision maker. In these settings, human review and domain-specific validation are part of the required system boundary.

## 8. Expected advantages

### 8.1 Open-world decision construction

The caller does not need to pre-enumerate every action. This addresses one of the biggest limitations of fixed-choice structured decision APIs.

### 8.2 Explicit set-level uncertainty

The system distinguishes “I strongly prefer A among these options” from “these options contain something worth doing.” This makes a major failure mode observable and measurable.

### 8.3 Adaptive compute rather than fixed candidate count

A fixed generate-`K`-then-rank pipeline spends the same generation budget whether the first candidate set is excellent or inadequate. Coverage-aware `EXPAND` allows the system to spend additional inference only on hard or incomplete states.

### 8.4 Multimodal decision making without collapsing images to captions

The intended architecture keeps image/screenshot input first-class for models that support it. Caption-only reduction remains a baseline, not the definition of multimodal performance.

### 8.5 Backend neutrality

Jev, Djev, cross-encoders, and native diffusion reads can be compared behind one decision contract. This makes empirical claims about latency/calibration separable from a single vendor or implementation.

### 8.6 Local-first deployment

A local DLM plus local backend can be used without transmitting application state to a hosted service. This matters for latency, privacy, reproducibility, and experimentation.

### 8.7 Potential unified diffusion runtime

The strongest systems hypothesis is that one multimodal DLM can support both `generate()` and `structured_read()` modes. If runtime state can be safely reused, this may reduce model duplication and service overhead relative to a generator-plus-separate-selector stack.

## 9. Expected disadvantages and technical risks

### 9.1 Candidate coverage is difficult to supervise

For many open-world tasks there is no exhaustive set of valid actions. The project therefore needs evaluation environments where acceptable action sets or environment success can be approximated reliably.

### 9.2 Generator and verifier errors may be correlated

If the same DLM fails to understand a state, it may both omit the correct action and incorrectly judge its own candidate set as adequate. Shared-backbone efficiency can therefore conflict with verifier independence.

This must be tested explicitly against independent backends and deliberately corrupted candidate sets.

### 9.3 Two-stage inference can erase latency gains

A local DLM generator followed by Djev is two diffusion passes. Until native/shared-runtime optimizations are proven, the system may be slower than a simpler encoder ranker.

### 9.4 Calibration under distribution shift is hard

`q_cov`, `q_sel`, and NOTA behavior may drift across domains, action-set sizes, visual distributions, and tool inventories. Raw model probabilities cannot be described as calibrated global success probabilities without evidence.

### 9.5 Dynamic candidate sets complicate probability comparison

A selection probability is conditioned on the current candidate set; changing or adding candidates changes the normalization context. Cross-state and cross-round comparisons require care.

### 9.6 Diffusion structured-read infrastructure is less mature

Djev-style seeded/pinned/read-only inference depends on relatively new engine capabilities. The project must isolate engine-specific behavior behind adapters and maintain deterministic mocks for core development.

### 9.7 Resource requirements

The default 26B-class model is substantial. Local GPU memory, startup time, checkpoint storage, and production serving complexity can make smaller encoders more practical in many applications.

### 9.8 More moving parts than fixed classification

Open generation, schema repair, candidate validation, backend read, calibration, and adaptive routing add failure modes. The architecture is justified only where the task truly needs open-world action construction.

## 10. Comparison with neighboring systems

### 10.1 Jev-like fixed structured decision systems

Their strength is fast, typed, probability-backed choice when the caller can specify the decision schema and options. Their limitation for this project is that action-space construction remains external.

Diffusion Decision moves candidate construction into the system and treats the quality/completeness of that generated set as an uncertain quantity.

### 10.2 Djev

Djev is an important implementation reference because it exposes Jev-style structured decisions over DiffusionGemma using seeded/pinned diffusion canvases and read-only log probabilities. It can also accept images.

The project differs in scope:

- Djev primarily performs a structured read over a supplied schema;
- Diffusion Decision includes candidate-space construction, candidate-set adequacy, adaptive expansion, backend comparison, and an eventual project-owned native read path;
- `DLM generator + Djev` is treated as a two-diffusion-stage baseline, not the final architecture.

### 10.3 Generate candidates + text encoder/ranker

This is the most important mature baseline. Candidate generation followed by ranking/verification is already widely used. The project does **not** claim this decomposition is new.

The differentiating question is whether the system can model **candidate-set failure** separately from within-set ranking and use that signal to drive adaptive computation.

### 10.4 Selective generation and NOTA

Prior selective-generation work already studies self-evaluation, candidate selection, and “None of the Above” as a way to reject poor candidate sets. NOTA is therefore not itself a novelty claim.

This project treats NOTA as one signal inside a richer action-space adequacy and controller framework.

### 10.5 Conformal candidate-set coverage

Conformal Language Modeling already studies how many generations are needed to construct a set that contains at least one acceptable output with a target coverage guarantee. Candidate-set coverage is therefore not an untouched research topic.

The project asks a different systems question: can a fast multimodal DLM directly provide useful runtime set-adequacy signals and use them to route between execution, expansion, abstention, and escalation under latency constraints?

### 10.6 Generative action sets in online decision making

Recent work on online decision making with generative action sets formalizes when an agent should pay a cost to create new actions. Dynamic action-set expansion itself is therefore not a novelty claim.

The intended contribution is the intersection of:

```text
multimodal DLM generation
+ structured probabilistic readout
+ explicit candidate-set adequacy
+ adaptive compute/risk routing
+ latency/calibration evaluation
```

## 11. Novelty boundaries: what this project must not claim

The project should **not** claim to have invented:

- generate → verify/rank → select;
- dynamic action generation;
- “None of the Above” rejection;
- candidate-set coverage as a general concept;
- conformal coverage guarantees;
- diffusion structured reads in general;
- Jev-style typed decision APIs.

These have clear precedents.

## 12. Proposed contributions

The paper-quality contribution package should instead be framed around the following combination.

### Contribution A — Generated decision-space uncertainty for fast multimodal agents

Formulate and empirically separate candidate-set adequacy from conditional selection confidence when the action set is generated by the model itself.

### Contribution B — Backend-neutral decision harness

Provide a reproducible harness that turns multimodal open-ended generation into a typed decision problem while preserving candidate identity, NOTA, tool validity, and comparable uncertainty outputs across Jev, Djev, encoder, and native DLM backends.

### Contribution C — DLM-native generate/read coupling

Implement a project-owned diffusion structured-read backend and evaluate the same multimodal diffusion backbone in two modes:

```text
generate candidates
structured probabilistic read
```

The scientific question is whether this coupling produces a useful latency/calibration trade-off, not merely whether it can be implemented.

### Contribution D — Coverage-aware adaptive compute controller

Use candidate-set adequacy and selection evidence to choose `ACT`, `EXPAND`, `ABSTAIN`, or `ESCALATE`, and quantify the improvement over fixed-`K` generation and forced top-1 selection.

### Contribution E — Controlled evaluation of candidate-set failure

Introduce candidate deletion, distractor injection, redundancy, missing-tool, and multimodal ambiguity tests that explicitly measure whether the system recognizes inadequate decision spaces rather than only reporting top-1 accuracy.

### Contribution F — Risk–latency evaluation

Report task success, calibration, miscoverage, unnecessary expansion, compute, memory, p50/p95 latency, and risk–latency Pareto curves instead of optimizing a single accuracy number.

## 13. Core research hypotheses

**H1 — Coverage signal:** a dedicated set-adequacy read predicts candidate-set failure better than top-1 selection confidence or entropy alone.

**H2 — Behavioral value:** routing on coverage reduces forced wrong actions under controlled candidate deletion without causing unacceptable over-expansion.

**H3 — DLM structured-read value:** native diffusion reads can match or improve useful calibration while achieving a competitive latency profile against a conventional cross-encoder baseline.

**H4 — Multimodal value:** direct multimodal state improves candidate coverage and end-to-end decision success over text-only/caption-only reductions on visual agent tasks.

**H5 — Adaptive compute:** variable expansion based on estimated set adequacy produces a better risk–latency frontier than fixed candidate counts.

**H6 — Runtime unification:** sharing a DLM runtime for generation and structured read reduces memory/service overhead and, where safe context reuse is possible, end-to-end latency.

**H7 — Correlated failure boundary:** an independent backend or deliberately decorrelated coverage model outperforms same-backbone self-verification on some candidate-generation failures; the project should quantify this rather than assume independence.

## 14. Paper-oriented narrative

A strong paper introduction can be built around the following sequence:

1. Fast decision models are attractive for agents because long autoregressive generation is expensive for every micro-decision.
2. Existing structured selectors typically assume a valid, externally specified action set.
3. Open-world agents must generate their own actions, creating a new failure mode: closed-set confidence can be high even when the set is inadequate.
4. Existing candidate-generation, NOTA, conformal-set, and generative-action-set work addresses related pieces but does not by itself answer the low-latency multimodal DLM systems question.
5. We build a backend-neutral harness that explicitly models candidate-set adequacy and conditional selection.
6. We implement and compare hosted, local diffusion, conventional encoder, and native diffusion decision backends.
7. We use the resulting uncertainty to control execution versus further computation and evaluate the risk–latency frontier.

## 15. Success criteria for the research program

The project is scientifically successful if it can demonstrate at least one robust result of the following form:

> At matched task risk, a coverage-aware adaptive system requires less latency/compute than fixed-generation baselines; or, at matched latency/compute, it reduces candidate-set-induced wrong actions.

The strongest result would additionally show that a native multimodal diffusion generate/read runtime contributes a measurable systems advantage beyond the general coverage-aware controller.
