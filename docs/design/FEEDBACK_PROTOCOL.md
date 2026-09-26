# Typed Low-Bandwidth Feedback Protocol

This file is the single source of truth for feedback codes, feedback payloads, loop context, and deterministic feedback compilation.

## 1. Purpose

DiCoJev closes the loop between structured decision evidence and open candidate generation without requiring a long free-form reasoning pass after every failed decision set.

The feedback path is:

```text
DecisionBackendResult
        |
        v
RiskController
  meta-action + FeedbackSignal(s)
        |
        v
FeedbackCompiler
        |
        v
GenerationFeedback / LoopContext
        |
        v
CandidateGenerator
```

The controller decides **what the system should do next**. The feedback compiler decides **the smallest structured information the generator needs to perform that next step**.

## 2. Feedback is not a backend wire field

Feedback is project-owned. Jev/Djev adapters return normalized evidence such as coverage, selection, NOTA, and diagnostics. They do not need to implement DiCoJev's feedback vocabulary.

A backend request remains backend-specific. Feedback begins only after backend evidence has been normalized.

## 3. Feedback codes

Stable initial vocabulary:

```text
ADEQUATE
MISSING_ACTION
AMBIGUOUS_SELECTION
INSUFFICIENT_INFORMATION
TOOL_MISMATCH
CONSTRAINT_FAILURE
REDUNDANT_SET
```

Meanings:

- `ADEQUATE` — current set is adequate enough for the controller policy.
- `MISSING_ACTION` — current set likely omits an acceptable qualitatively distinct action.
- `AMBIGUOUS_SELECTION` — the set may be adequate, but no supplied candidate is sufficiently preferred.
- `INSUFFICIENT_INFORMATION` — the state/goal evidence is inadequate to make a safe next-action decision.
- `TOOL_MISMATCH` — candidates depend on unavailable or invalid tools/capabilities.
- `CONSTRAINT_FAILURE` — candidates materially violate stated constraints.
- `REDUNDANT_SET` — the set spends capacity on duplicates/paraphrases and needs more diversity.

The vocabulary is deliberately small. New codes require an explicit design change because each code affects generation behavior and evaluation.

## 4. `FeedbackSignal`

Conceptual schema:

```json
{
  "code": "MISSING_ACTION",
  "severity": 0.83,
  "focus_candidate_ids": ["A", "B"],
  "evidence_refs": ["coverage.raw", "selection.nota_probability"],
  "details": {
    "requested_new_candidates": 3
  }
}
```

Rules:

- `code` is mandatory and typed.
- `severity` is optional evidence strength, not automatically calibrated probability.
- `focus_candidate_ids` may identify candidates relevant to the feedback without changing their semantics.
- `evidence_refs` points to normalized evidence fields used to derive the signal.
- `details` is schema-bounded metadata; it must not become an unbounded natural-language reasoning channel.

## 5. `FeedbackBundle`

A controller may emit multiple compatible signals for one decision round. The bundle contains:

```text
primary signal
secondary signals (optional)
source round
controller reason code
generation relevance
```

Contradictory combinations must be rejected or normalized deterministically. For example, `ADEQUATE` cannot be the primary signal while `MISSING_ACTION` is simultaneously treated as a required expansion condition.

## 6. Meta-actions remain separate

Feedback describes *why* the current decision state has a problem. Controller actions describe *what happens next*:

```text
ACT
EXPAND
ABSTAIN
ESCALATE
```

Examples:

```text
MISSING_ACTION          -> EXPAND
REDUNDANT_SET           -> EXPAND
INSUFFICIENT_INFORMATION -> ABSTAIN or ESCALATE
TOOL_MISMATCH           -> EXPAND or ESCALATE
ADEQUATE                -> ACT (if selection/risk thresholds also pass)
```

These mappings are policy decisions and may vary by controller configuration.

## 7. `LoopContext`

Every regeneration round receives a backend-neutral loop context containing at least:

```text
round_index
prior semantic candidates with stable IDs
prior candidate provenance
latest FeedbackBundle
feedback history summary
remaining candidate budget
remaining expansion budget
remaining latency/compute budget
```

Raw model chain-of-thought is not part of `LoopContext`.

## 8. `FeedbackCompiler`

`FeedbackCompiler` is deterministic for a fixed input configuration. It maps typed feedback into generator-facing constraints/instructions.

Example:

```text
FeedbackSignal(code=MISSING_ACTION)
        |
        v
"The current candidate set likely omits an acceptable action.
 Preserve existing candidates. Generate up to 3 qualitatively different
 alternatives. Do not paraphrase existing actions."
```

Example:

```text
FeedbackSignal(code=TOOL_MISMATCH)
        |
        v
"Generate alternatives using only tools declared in the request.
 Do not repeat candidates requiring unavailable tools."
```

The text template may be replaced by structured model input later, but the semantic mapping from feedback code to regeneration constraint remains explicit and testable.

## 9. Low-bandwidth constraint

The project should be able to measure the information passed through feedback independently of the generator output. At minimum record:

```text
feedback code count
serialized feedback bytes/tokens
number of referenced candidate IDs
compiled feedback prompt tokens (when text templates are used)
```

The project must not claim a token-efficiency advantage until it is measured against a named long-form or free-form feedback baseline.

## 10. Failure policy

- Unknown feedback codes fail validation.
- Feedback compilation failure must not default to `ACT`.
- Missing evidence references are diagnostic errors, not reasons to fabricate confidence.
- Unbounded free-form feedback is not allowed in the canonical protocol.
- If the system needs information outside the generator's scope, use `ABSTAIN`/`ESCALATE` rather than pretending another candidate-generation round can solve the problem.

## 11. Research use

The protocol enables experiments comparing:

```text
no feedback
binary retry signal
DiCoJev typed feedback
long-form LLM feedback
```

under matched candidate budgets, recovery tasks, latency, and feedback-token budgets.
