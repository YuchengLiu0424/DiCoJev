# Final Project Review — 1.0.0 (research milestone v5)

Review date: 2026-09-30

## Executive verdict

DiCoJev is complete as a coherent research-software project. Its strongest result is not that a
particular diffusion model wins on accuracy or latency; the current evidence does not support that
claim. Its strongest result is a tested architecture that makes uncertainty about a generated
decision space explicit, routes that evidence through a bounded controller, and records enough
structure to audit what happened.

The v5 code, offline demonstration, API surface, evaluation artifact, packaging, and documentation
form a usable 1.0 release candidate. Publication is an operational step still separate from this
review: the v5 branch must be pushed, reviewed, merged, and tagged before GitHub presents it as the
released default.

## What the final system does

1. Accepts multimodal state, a goal, available tools, constraints, and a compute budget.
2. Generates a bounded semantic candidate set.
3. Preserves stable candidate identity while validating syntax, tools, constraints, and redundancy.
4. Estimates candidate-set coverage separately from within-set selection.
5. Emits `ACT`, `EXPAND`, `ABSTAIN`, or `ESCALATE` with typed evidence.
6. Compiles bounded feedback into another generation round when expansion is justified.
7. Crosses an allowlisted execution boundary only after `ACT`.
8. Records the action result and structured environment transition.

The final local topology uses one LLaDA-V service for candidate generation and native reads.
Provider-specific alternatives remain behind generator/backend contracts.

## Acceptance review

| Area | Status | Evidence |
|---|---|---|
| Schemas and contracts | Pass | strict Pydantic request, candidate, evidence, feedback, response, and execution models |
| Closed-loop behavior | Pass | 11/11 controlled cases; all four controller actions represented |
| Multimodal transport | Pass with scope limit | native image payload and one controlled multimodal loop; prior live LLaDA image evidence |
| Feedback/rethink harness | Pass | typed feedback changes subsequent candidate generation and is measured in bytes/tokens |
| Action safety | Pass | allowlisted handlers, normalized failures, no generated shell execution |
| API | Pass | health and decision endpoints return the complete typed trace |
| Packaging | Pass | wheel build and clean-environment install/import smoke |
| Documentation | Pass after final audit | current v5 quickstart, runtime path, evidence limits, comparison, ownership check |
| Offline quality gates | Pass | 116 tests, Ruff formatting/lint, link ownership validation |
| Optional service gates | Not part of offline pass | six tests require explicitly enabled model/provider services |
| General empirical superiority | Not established | small live studies are mixed or negative |
| GPU performance characterization | Open hardware limitation | v5 host run did not produce a valid model GPU-memory measurement |

## Evidence interpretation

Positive evidence:

- controlled omission, ambiguity, redundancy, tool mismatch, constraint failure, and insufficient
  information lead to the intended controller behavior;
- live Jev evidence reacts to deletion of acceptable actions;
- local LLaDA structured reads are repeatable under the recorded configuration;
- one loaded local runtime can serve generation and structured reads;
- cached native-image processing preserved the recorded decision while improving the measured
  sequential CPU path;
- the full tool result and state transition are represented in the final response.

Negative or inconclusive evidence retained by design:

- typed feedback did not beat binary or long-form feedback in the small live policy study;
- learned adaptive compute did not beat fixed policies there;
- local native LLaDA coverage was weaker than hosted Jev on the matched six-set study;
- local CPU inference is correct but too slow for an interactive product;
- controlled fixtures validate mechanisms but cannot substitute for a broad task benchmark.

These findings are why v5 ships the threshold controller and describes adaptive compute as an
experimental option.

## Advantages relative to adjacent projects

The following are architectural advantages for DiCoJev's intended problem, not broad rankings.

### Compared with general orchestration frameworks

LangGraph, Microsoft Agent Framework, and similar systems provide richer workflow persistence,
multi-agent coordination, integrations, deployment, and observability. DiCoJev provides a more
specialized decision primitive: it asks whether a model-generated choice set is adequate before
allowing selection or execution. It can sit inside those systems; it does not replace them.

### Compared with lightweight tool/code agents

smolagents and comparable tool agents make it easy for a model to choose and invoke tools. DiCoJev
adds an explicit pre-execution rejection layer over several generated alternatives, preserves
coverage and selection as different quantities, and uses bounded feedback to repair the choice set.
It is preferable only when missing-choice risk is central enough to justify the extra reads.

### Compared with Jev/Djev-style structured selection

Jev and Djev answer structured questions over supplied alternatives. DiCoJev owns the surrounding
open-world loop: construct alternatives, detect candidate-set inadequacy, regenerate with typed
feedback, and abstain or escalate. When the input taxonomy is known complete, the simpler structured
selector is likely the better system.

### Compared with ordinary generate-then-rank pipelines

A ranker normally supplies a relative ordering but does not prove that any candidate is acceptable.
DiCoJev requires a set-level adequacy signal and makes NOTA, abstention, escalation, budgets, and
feedback costs explicit. Its cost is additional complexity and, often, additional model calls.

## Reproducibility review

The project is reproducible at three levels:

- **Zero-service:** install the package, run `examples/v5_offline_agent.py`, run the test suite, and
  recreate `benchmarks/v5_evaluation.json`.
- **Local model:** install the external LLaDA-V checkpoint/source, run the repository server, then
  execute generation and native-read smoke tests.
- **Hosted comparison:** provide credentials explicitly and run the named live scripts, which
  persist normalized evidence without credentials.

The repository does not bundle large weights, provider credentials, or the upstream LLaDA-V code.
Exact live reproduction therefore depends on those external assets and the recorded configuration.

## Maintainability review

Strengths:

- strict backend-neutral contracts;
- optional dependencies isolated by feature;
- unit tests do not depend on services;
- release evidence is normalized and committed;
- raw and calibrated values remain distinct;
- documentation has explicit ownership and a link checker;
- provider or tool failure is fail-closed.

Remaining engineering debt:

- no durable session store, distributed queue, authentication, rate limiting, or production
  observability layer;
- adaptive-policy artifacts are injectable but not managed by an operator-facing registry;
- model-server installation is bespoke and tied to upstream LLaDA-V source compatibility;
- broader benchmark datasets and accelerator measurements would be required for research claims
  beyond architectural feasibility.

## Final use recommendation

Use DiCoJev as:

- a research harness for generated-action-set failure;
- a decision safety layer inside a larger agent workflow;
- a reproducible comparison surface for coverage, selection, feedback, and compute policies;
- a local/private multimodal prototype when CPU latency is acceptable.

Do not present it as:

- a proven replacement for general agent frameworks;
- a production-ready autonomous execution platform;
- evidence that diffusion agents are generally faster or more accurate;
- a validated safety system for high-stakes deployment.

With those boundaries, v5 is a defensible final project: the software is integrated, the entry path
is understandable, the claims match the evidence, and negative results are part of the deliverable
rather than hidden.
