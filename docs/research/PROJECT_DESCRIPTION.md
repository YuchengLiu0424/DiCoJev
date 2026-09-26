# DiCoJev Research Project Description

## 1. Research thesis

DiCoJev studies a specific failure mode in fast structured decision systems: **selection confidence is conditional on the candidate set, but the candidate set may itself be generated, incomplete, or malformed**.

A model can be highly confident about the best member of `C` while the actually acceptable action is absent from `C`. DiCoJev therefore treats generated decision-space uncertainty as a first-class variable and asks whether compact structured feedback can close the loop without requiring repeated long-form LLM deliberation.

The core research question is:

> Can a multimodal diffusion model construct an action set, receive low-bandwidth structured evidence about whether that set is adequate, and iteratively reach a reliable decision with lower latency/token cost than long-form generate-reason-regenerate pipelines?

## 2. Formal problem

Given multimodal state `x`, goal `g`, tools/constraints `T`, and bounded history, a candidate generator produces:

```text
C_t = G_theta(x, g, T, loop_context_t)
```

Let `A*(x,g,T)` be the set of acceptable next semantic actions.

Candidate-set adequacy is:

```text
y_cov = 1[C_t intersects A*]
```

and the system estimates `q_cov`. A decision backend separately produces within-set selection evidence `q_sel`.

The controller chooses:

```text
u_t in {ACT, EXPAND, ABSTAIN, ESCALATE}
```

and a typed feedback signal `f_t` such as:

```text
MISSING_ACTION
AMBIGUOUS_SELECTION
INSUFFICIENT_INFORMATION
TOOL_MISMATCH
CONSTRAINT_FAILURE
REDUNDANT_SET
```

When `u_t = EXPAND`, the harness deterministically compiles `f_t` into the next `loop_context` rather than asking a general LLM to narrate a new reasoning trace.

## 3. Why diffusion

The project deliberately investigates DLMs instead of simply attaching an autoregressive LLM to a structured selector. The hypothesis is that diffusion inference can provide a useful combination of:

- parallel generation/refinement;
- multimodal image-text state ingestion;
- fast small-output structured reads demonstrated by Djev-like techniques;
- one model family that can potentially support both open candidate generation and compact probabilistic readout.

DLM use is a research hypothesis, not an assumption that diffusion is always faster or better. Conventional cross-encoders and hosted/local structured decision systems remain required baselines.

## 4. Why the harness matters

The harness is not treated as glue. It is the semantic control plane between two different inference regimes:

```text
open world:   generate possible semantic actions
closed world: evaluate a compact temporary candidate set
open world:   regenerate only when typed evidence says the set is inadequate
```

It owns stable candidate identity, normalization, constraint checks, NOTA insertion, backend compilation, loop state, and typed feedback compilation.

The feedback channel is intentionally low-bandwidth. The project asks whether a small discrete control vocabulary can recover from candidate omission nearly as well as a verbose free-form critique while reducing latency and generated tokens.

## 5. Application scenarios

### GUI and computer-use agents
A screenshot may admit many possible UI actions, and the useful action can be missing from the first generated set. DiCoJev can detect set inadequacy, request alternatives, and avoid executing a high-confidence bad choice.

### Tool-using software agents
Available tools and argument constraints change dynamically. Coverage and typed tool-mismatch feedback can prevent the selector from choosing among actions that all rely on unavailable capabilities.

### Customer-support workflow routing
The next action may be dynamically constructed from policy, account state, and customer intent. A small structured controller can request alternative workflows or abstain rather than force a closed taxonomy.

### Embodied/simulated agents
Perception is multimodal, action sets vary by state, and latency matters. Explicit set adequacy is useful when perception or action construction is incomplete.

High-stakes domains should be treated as research/human-gated settings until reliability is independently validated.

## 6. Expected advantages

- Explicitly separates **set adequacy** from **within-set confidence**.
- Allows high-confidence forced-choice errors to be converted into `EXPAND`, `ABSTAIN`, or `ESCALATE`.
- Can reuse a compact structured backend instead of invoking a long reasoning generation for every control step.
- Keeps Jev/Djev/cross-encoder/native DLM reads interchangeable.
- Makes token/latency cost of the feedback loop measurable.
- Supports local/private multimodal deployments.

## 7. Structural disadvantages and risks

### Coverage supervision
Open action spaces rarely have a complete oracle. Early evaluation should use environments with labeled acceptable-action sets or controlled candidate corruption.

### Correlated self-evaluation
If the same DLM generates candidates and judges coverage, failures may be correlated. The project therefore supports independent coverage backends and measures same-backbone versus independent-verifier error correlation.

### Double diffusion cost
DLM generation followed by a Djev backend performs two diffusion passes and may erase latency advantages. It is a baseline, not the intended final topology.

### Feedback-code insufficiency
A compact vocabulary may omit nuances that a free-form critique captures. This must be tested directly rather than assumed.

### Calibration shift
`q_cov` and `q_sel` can drift under distribution change, candidate-set size changes, and multimodal shifts.

### Hardware cost
A 26B-class local model remains expensive even if only a subset of parameters is active per token/step.

### Fixed-taxonomy tasks
When the action set is truly fixed, a conventional classifier may be simpler and superior. DiCoJev is aimed at dynamically constructed decision spaces.

## 8. Relationship to Jev and Djev

Jev-style systems efficiently answer structured questions over supplied criteria. Djev demonstrates Jev-like structured reads using DiffusionGemma. DiCoJev treats both as possible decision backends.

The project-level distinction is not merely “DLM before Djev.” It is:

```text
self-generated action set
+ explicit set-coverage evidence
+ typed low-bandwidth feedback
+ closed-loop candidate refinement
+ pluggable structured decision backend
```

Djev can be wrapped in an external loop, but candidate-set adequacy and the generation-feedback-control protocol are not the core abstraction of Djev itself.

## 9. Proposed research contributions

The intended contribution package is:

1. **Generated decision-space uncertainty** — formal separation of candidate-set adequacy and conditional selection evidence in a fast multimodal agent architecture.
2. **Typed low-bandwidth feedback loop** — a project-owned protocol that converts compact structured evidence into targeted regeneration without requiring long-form reasoning at every retry.
3. **Backend-neutral decision harness** — a reproducible semantic bridge between diffusion generation, set management, structured decision backends, and feedback-controlled expansion.
4. **DLM-native generate/read coupling** — evaluation of one diffusion model family for both open candidate generation and compact structured readout.
5. **Controlled candidate-set failure evaluation** — explicit deletion, distractor, redundancy, tool-mismatch, and information-deficiency tests.
6. **Risk-latency-token evaluation** — comparison of success/recovery, calibration, GPU/latency cost, and feedback bandwidth.

These are intended as a combined system/research contribution. Individual ingredients have substantial prior art and should not be presented as independently invented.

## 10. Paper starting point

A potential paper framing is:

> **DiCoJev: Coverage-Aware Jev-Style Decision Making over Diffusion-Generated Action Sets with Low-Bandwidth Feedback**

A strong paper must demonstrate that explicit coverage plus typed feedback improves decision reliability or efficiency under controlled candidate-set failure, rather than merely showing that a DLM can generate options and a selector can rank them.
