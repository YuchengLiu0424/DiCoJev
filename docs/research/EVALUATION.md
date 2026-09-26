# Evaluation Plan

This file owns research hypotheses, benchmark construction, metrics, and ablations.

The first small v1 integration run is recorded in `V1_EVALUATION.md`. It validates shared
candidate-set transport and establishes the runner, but it is not evidence for the broader
coverage/recovery hypotheses below.

## Evaluation progression

Evaluation is deliberately staged with implementation maturity. The project should not replace
its small deterministic tests with a large external benchmark prematurely, nor present integration
fixtures as evidence of general decision-making ability.

1. **Repository smoke suite.** Keep the current five-case v1 text set as a fast, inexpensive,
   human-auditable integration check. It verifies candidate transport, backend normalization,
   metrics, and reproducibility. It is not an ability benchmark.
2. **Policy-grounded text and tool decisions.** As the v2 closed loop becomes stable, import a
   small, version-pinned slice of published benchmark episodes—starting with τ-bench—while
   preserving the original state, tools, policy, reference actions, and executable evaluator.
   Decision checkpoints should be derived from released episodes rather than replaced with newly
   invented trivia or obvious safety questions.
3. **Adversarial agent decisions.** Add an AgentDojo slice when tool authorization, untrusted
   observations, and fail-closed behavior can be represented faithfully. Measure utility and
   security separately.
4. **Stateful and multimodal operation.** Add ToolSandbox-style stateful conversations and then
   OSWorld/WorkArena tasks only when the corresponding tool, image, and computer-state paths are
   implemented. A benchmark must not be reduced to a text-only proxy that removes its defining
   difficulty.
5. **Full comparative evaluation.** Once DiCoJev is feature-complete for a benchmark condition,
   compare it with named strong conventional LLM/agent baselines under matched observations,
   tools, action budgets, and execution evaluators.

For every imported checkpoint, distinguish four outcomes: both systems succeed; DiCoJev alone
succeeds; the conventional baseline alone succeeds; or both fail. DiCoJev failures must then be
localized to candidate omission, redundancy, false coverage, incorrect selection, unnecessary
abstention, or failed feedback recovery. Cases where a strong baseline succeeds and DiCoJev fails
define the empirical capability boundary and must be retained rather than tuned away.

External benchmark data must remain version-pinned and attributable. Prefer adapters that consume
the upstream dataset and evaluator over copying or rewriting benchmark questions into this
repository. Record licenses, dataset splits, checkpoint-selection rules, and any transformation of
the original observation or action space.

## 1. Core hypotheses

H1. `q_cov` contains useful information about candidate-set adequacy beyond `q_sel` and top-1 score.

H2. Coverage-aware routing reduces wrong `ACT` decisions when acceptable actions are removed from the candidate set.

H3. Typed feedback improves recovery after candidate-set failure relative to blind retry under matched generation budgets.

H4. Typed feedback can approach or exceed long-form feedback recovery while consuming fewer feedback tokens and less latency.

H5. Native DLM structured read can improve the risk-latency/memory trade-off relative to a two-service DLM + Djev topology.

H6. Same-backbone generation/verification has measurable correlated failure that can be reduced by an independent coverage verifier in some settings.

## 2. Controlled candidate-set corruptions

At minimum generate conditions that:

- remove all acceptable actions;
- remove only the best/preferred acceptable action;
- inject plausible distractors;
- duplicate/paraphrase semantic actions;
- introduce unavailable-tool actions;
- introduce constraint-violating actions;
- vary candidate-set size;
- degrade or hide necessary multimodal information;
- create ambiguous-but-covered sets.

## 3. Decision metrics

- candidate coverage / miscoverage;
- coverage Brier score / ECE where probability interpretation is valid;
- false-adequate rate;
- conditional selection accuracy given coverage;
- NOTA precision/recall where applicable;
- wrong-ACT rate;
- unnecessary-EXPAND rate;
- EXPAND recovery rate;
- abstention/escalation utility.

## 4. Feedback metrics

- recovery rate by feedback code;
- feedback-code accuracy against labeled failure type where available;
- number of feedback signals per round;
- serialized feedback bytes/tokens;
- compiled feedback prompt tokens;
- regeneration diversity after `MISSING_ACTION` / `REDUNDANT_SET`;
- tool-validity recovery after `TOOL_MISMATCH`;
- success per feedback token;
- latency attributable to feedback processing.

## 5. System metrics

- p50/p95 end-to-end latency;
- generator latency;
- backend latency;
- harness/controller/feedback compilation latency;
- number of generation rounds;
- total generated tokens / diffusion steps;
- GPU memory;
- compute per successful decision.

## 6. Required feedback baselines

Compare at least:

```text
A. no retry / forced selection
B. blind retry on low confidence
C. binary retry signal only
D. DiCoJev typed feedback
E. long-form model/verifier feedback
```

Where possible match total candidate budgets and report both success and feedback bandwidth.

## 7. Backend baselines

Use identical normalized candidate sets as far as modality capabilities allow:

- JevCloud;
- DjevLocal;
- CrossEncoder;
- NativeDLMDecisionBackend;
- mock/oracle components for controlled studies.

Captioning or other preprocessing that changes evidence must be a named experimental condition.

## 8. Core ablations

- no coverage;
- `q_sel` used as a deliberately weak coverage proxy;
- NOTA only;
- no candidate deduplication;
- fixed candidate budget vs adaptive expansion;
- no typed feedback / binary feedback / full typed feedback;
- remove individual feedback codes;
- same-DLM verifier vs independent verifier;
- Djev vs NativeDLM read;
- raw vs calibrated evidence;
- caption baseline vs native multimodal path;
- separate model services vs shared runtime.

## 9. Reporting principle

The primary claim should be supported by **risk-latency-token Pareto comparisons**, not only top-line accuracy. Recorded run artifacts must be sufficient to reproduce core tables and plots.
