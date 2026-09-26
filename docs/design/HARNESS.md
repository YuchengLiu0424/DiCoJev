# Decision Harness Specification

This file owns how raw DLM generation becomes a deterministic, backend-neutral decision problem.

## 1. Why the harness exists

Open-ended model output is not a stable API. Provider-specific decision JSON is also not an appropriate generator contract. The harness isolates probabilistic semantic generation from deterministic validation and compilation.

The generator therefore targets `DecisionSpec`, not Jev/Djev wire JSON.

## 2. Transformation pipeline

```text
DecisionRequest
   |
   v
prompt / multimodal message construction
   |
   v
raw DLM generation
   |
   v
JSON extraction
   |
   v
bounded repair
   |
   v
schema validation
   |
   v
candidate normalization
   |
   v
deduplication
   |
   v
tool / constraint validation
   |
   v
stable ID assignment
   |
   v
synthetic NOTA insertion
   |
   v
backend compiler
   |
   v
DecisionBackendRequest
```

## 3. Generator output contract

The DLM should output only project-native semantic content needed to construct `DecisionSpec`.

It should not be instructed to invent:

- backend credentials;
- Jev model names;
- probability fields;
- calibrated confidence;
- candidate IDs whose tokenization is backend-specific;
- controller meta-actions as ordinary semantic candidates.

## 4. JSON extraction and repair

Repair must be bounded and observable.

Recommended policy:

1. accept valid JSON object;
2. extract one fenced/raw JSON object if surrounding prose exists;
3. perform at most one deterministic/specified repair strategy;
4. validate with Pydantic;
5. fail with `InvalidDecisionSpec` if still invalid.

Do not repeatedly ask the model to self-repair in an unbounded loop.

## 5. Candidate normalization

For every candidate:

- trim superficial formatting;
- preserve original semantic text for traceability;
- normalize obvious whitespace/casing only for duplicate keys;
- validate structured tool/action fields;
- reject or flag empty actions;
- attach provenance (`generation_round`, raw index).

## 6. Deduplication

Deduplication operates before compact label assignment.

At minimum support:

- normalized exact match;
- configurable semantic duplicate detection later.

When semantic deduplication merges candidates, preserve all source provenance and record the representative chosen.

## 7. Candidate IDs

The harness assigns stable compact IDs after deduplication:

```text
A, B, C, ...
```

IDs must be deterministic given ordered normalized candidates. Expansion should preserve IDs of prior candidates wherever possible and allocate new IDs only to genuinely new candidates.

## 8. NOTA injection

`N = None of the above` is injected by the harness for backends that support/require an explicit reject option.

Rules:

- do not ask the generator to create NOTA;
- mark it `synthetic=true`;
- exclude it from semantic candidate coverage calculations;
- record its backend probability separately when useful.

## 9. Backend compiler

Compilation is backend-specific but deterministic. Examples:

- Jev/Djev compiler -> `state + questions` with `noul` coverage and `choice` selection;
- cross-encoder compiler -> per-candidate feature pairs plus set-level coverage input;
- native DLM compiler -> structured read template/canvas.

No compiler is allowed to reinterpret the semantic action set without recording that transformation.

## 10. Expansion loop

When the controller returns `EXPAND(k)`, the next generator request includes:

- original state/goal/tools/constraints;
- previous semantic candidates;
- reason for expansion;
- instruction to add missing qualitatively different actions rather than paraphrases;
- remaining candidate budget;
- remaining latency/compute budget.

New and old candidates are merged through the same validation/deduplication path.

## 11. Traceability

For each round, record:

```text
raw generator output hash or opt-in text
validated DecisionSpec
candidate set before/after dedupe
candidate IDs
quality flags
backend request metadata
backend normalized result
controller decision
latency by component
```

Raw image bytes are excluded from telemetry by default.
