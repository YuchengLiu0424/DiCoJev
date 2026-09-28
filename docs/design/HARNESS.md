# Decision Harness Specification

This file owns how raw DLM generation becomes a deterministic backend-neutral decision problem and how typed feedback is compiled into the next generation round.

## 1. Why the harness exists

Open model output is not a stable API. Provider-specific decision JSON is not an appropriate generator contract. The harness separates probabilistic semantic generation from deterministic validation, decision compilation, candidate management, and feedback compilation.

The generator targets `DecisionSpec`, not Jev/Djev wire JSON.

## 2. Forward transformation

```text
DecisionRequest
   -> generation input construction
   -> raw DLM generation
   -> JSON extraction
   -> bounded repair
   -> schema validation
   -> candidate normalization
   -> deduplication
   -> tool / constraint validation
   -> stable ID assignment
   -> synthetic NOTA insertion
   -> backend compiler
   -> DecisionBackendRequest
```

## 3. Generator output contract

The DLM emits project-native semantic content. It must not be asked to invent backend credentials, Jev model names, probability fields, calibrated confidence, backend-specific token IDs, NOTA, or controller meta-actions.

## 4. Parsing and bounded repair

1. accept a valid JSON object;
2. extract one fenced/raw JSON object if surrounding prose exists;
3. perform at most one configured deterministic repair strategy;
4. validate with Pydantic;
5. fail with `InvalidDecisionSpec` if still invalid.

Unbounded self-repair loops are forbidden in the canonical harness.

## 5. Candidate normalization and registry

For each semantic candidate:

- preserve original semantic text for traceability;
- normalize superficial formatting only for canonical keys;
- validate structured tool/action fields;
- reject/flag empty actions;
- attach generation-round provenance;
- deduplicate before compact-label assignment;
- preserve stable IDs across expansion rounds whenever semantics remain unchanged.

The reference quality pass records invalid formatting, unavailable tools, explicitly declared
constraint violations, and token-overlap redundancy groups. These flags remain separate from
backend coverage evidence. Explicit constraint violations are carried on the candidate rather
than inferred from unrestricted natural-language reasoning.

## 6. NOTA

Synthetic `N = None of the above` is injected only for compatible backends. The generator does not create it. It is `synthetic=true` and excluded from semantic candidate coverage calculations.

## 7. Decision compilers

Examples:

- Jev/Djev -> `noul` coverage + `choice` selection;
- cross-encoder -> per-candidate scoring + separate set-level coverage method;
- native DLM -> structured-read template/canvas.

A compiler may not silently reinterpret the semantic action set.

## 8. Feedback path

After backend normalization:

```text
DecisionBackendResult
   -> RiskController
   -> MetaAction + FeedbackBundle
   -> FeedbackCompiler
   -> LoopContext
   -> CandidateGenerator (when EXPAND)
```

The feedback compiler is deterministic and follows `FEEDBACK_PROTOCOL.md`. It does not infer whether expansion is required; that is the controller's job.

## 9. Expansion loop

When the controller returns `EXPAND(k)`, `LoopContext` contains:

- original state/goal/tools/constraints;
- all prior semantic candidates and stable IDs;
- latest typed feedback bundle;
- feedback-history summary;
- requested number of new candidates;
- remaining candidate/round/latency/compute budgets.

The generator is instructed to add qualitatively new candidates rather than paraphrase existing ones. New and old candidates pass through the same validation and deduplication path.

## 10. Feedback compilation examples

`MISSING_ACTION` compiles to a regeneration constraint that preserves prior actions and requests semantically distinct alternatives.

`TOOL_MISMATCH` compiles to a restriction that new actions use only available tools.

`REDUNDANT_SET` compiles to an explicit diversity requirement.

`INSUFFICIENT_INFORMATION` normally should not be converted into blind regeneration unless controller policy has an information-gathering generation strategy; otherwise the controller should ABSTAIN or ESCALATE.

## 11. Traceability

For every round record:

```text
raw generator output hash or opt-in text
validated DecisionSpec
candidate set before/after dedupe
stable candidate IDs and provenance
candidate quality flags
backend request metadata
normalized backend result
feedback bundle
serialized/compiled feedback size
controller decision
latency by component
remaining budget
```

Raw image bytes are excluded from telemetry by default.

## 12. v2 budget accounting

The reference loop charges one compute unit for candidate generation and one for a backend read.
An expansion begins only when two compute units remain. Wall-clock latency is measured from loop
entry, and a completed evidence read may still result in `ACT`; exhausted latency prevents another
expansion. Traces record remaining candidate, expansion, latency, and compute budgets after each
round.

Initial generation reserves candidate capacity across the configured maximum number of rounds
rather than consuming the total candidate budget before feedback can request an expansion.
