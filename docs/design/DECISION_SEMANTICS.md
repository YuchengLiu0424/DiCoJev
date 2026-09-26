# Decision Semantics and Schemas

This file is the single source of truth for coverage, selection confidence, candidate quality, NOTA, controller actions, and normalized data shapes.

## 1. Three schema layers

The system has three explicit representations:

1. **Public project request/response** — backend-neutral API.
2. **`DecisionSpec`** — generator-produced internal representation.
3. **Backend wire schema** — Jev/Djev/cross-encoder/native implementation detail.

A DLM is not required to emit backend wire JSON directly.

## 2. Candidate set

Let:

```text
C = {a1, ..., aK}
```

be the semantic candidates produced by the generator after harness normalization.

The harness assigns compact IDs such as `A`, `B`, `C`. IDs are transport identifiers, not action semantics.

A synthetic `N = None of the above` may be added for decision backends. `N` is **not** considered a generated semantic action and is excluded from candidate coverage ground truth.

## 3. Acceptable action set

For evaluation, define:

```text
A*(x, g, T)
```

as the set of acceptable next semantic actions given state `x`, goal `g`, and available tools/constraints `T`.

Use multiple acceptable actions when the environment permits them. Do not force a unique gold action only to simplify evaluation.

## 4. Candidate-set coverage event

Ground-truth adequacy is:

```text
y_cov = 1 if C intersects A* else 0
```

The model/backend estimate is:

```text
q_cov ~= P(y_cov = 1 | x, g, T, C)
```

`q_cov` is a model score until calibration is demonstrated. Documentation may call it a coverage probability only when the backend genuinely exposes a probability-like binary output; even then it must not be described as calibrated without evidence.

## 5. Selection evidence

A backend returns a distribution or score over supplied candidate IDs, possibly including `N`.

The selected semantic candidate is:

```text
a_hat = argmax over executable non-synthetic choices according to backend/controller policy
```

`q_sel` means evidence/confidence for the selected candidate **conditional on the current candidate set**. It is not a global success probability.

For evaluation:

```text
y_sel = 1 if a_hat in A* else 0
```

Selection accuracy should also be reported conditional on `y_cov = 1`, because no selector can recover an absent acceptable candidate without expansion.

## 6. Joint proxy

The engineering feature:

```text
q_joint_proxy = q_cov * q_sel
```

may be logged or used by a policy experiment, but is not automatically equal to:

```text
P(task success)
```

A stronger interpretation requires explicit calibration and dependence analysis.

## 7. Candidate quality

Candidate quality is separate from both coverage and selection. Signals may include:

```text
syntactic_validity
executability
tool_availability
constraint_compliance
redundancy_group
diversity_score
expected_utility
expected_cost
```

A set can have individually valid candidates while still missing every acceptable action. Conversely, a set can have adequate coverage while also containing invalid distractors.

## 8. NOTA semantics

`N = None of the above` means:

> the structured decision backend judges that none of the supplied semantic candidates should be selected.

NOTA is **not identical** to:

- low `q_cov`;
- `ABSTAIN`;
- `EXPAND`;
- `ESCALATE`.

It is backend evidence that the controller may use. For example, a controller might respond to high NOTA probability with `EXPAND` while budget remains, then `ABSTAIN` after budget exhaustion.

## 9. Controller meta-actions

### ACT

Execute a selected semantic action because policy thresholds/risk criteria are satisfied.

### EXPAND

Request additional **new semantic alternatives** from the generator while preserving prior candidates and remaining budget.

### ABSTAIN

Take no environment action and return a typed decision indicating insufficient confidence/information or exhausted safe options.

### ESCALATE

Transfer the decision to a slower/higher-authority target such as a planner, stronger model, or human review endpoint.

These are controller actions and are not mixed into the candidate list as ordinary semantic actions.

## 10. Stable `DecisionSpec`

Conceptual form:

```json
{
  "schema_version": "1",
  "task": "Choose the best next action",
  "decision_type": "choice",
  "candidates": [
    {
      "action": "Review recipients before sending",
      "tool": "ui.click",
      "arguments_hint": {"target": "recipient field"}
    }
  ],
  "selection_instruction": "Choose the safest useful next action toward the goal.",
  "coverage_instruction": "Determine whether at least one candidate is acceptable as the next action.",
  "constraints": [
    "Do not invent unavailable tools",
    "Do not repeat semantically equivalent candidates"
  ]
}
```

Provider-specific request/response fields must not leak into this representation.

## 11. Jev-compatible compilation

Coverage is compiled as a `noul` question:

```json
{
  "type": "noul",
  "instructions": "Does candidate_set contain at least one acceptable next action for the stated goal?",
  "criteria": {
    "true": "At least one candidate is an acceptable next action.",
    "false": "No candidate is acceptable or a materially necessary action is missing."
  }
}
```

Selection is compiled as `choice`:

```json
{
  "type": "choice",
  "instructions": "Choose the best acceptable next action. Choose N if none is acceptable.",
  "criteria": {
    "A": "Review recipients",
    "B": "Click Send",
    "N": "None of the above"
  }
}
```

This preserves Jev's `type / instructions / criteria` model. Coverage lives in the answer to a separate binary question rather than in a new fourth question component.

## 12. Normalized backend result

Conceptual form:

```json
{
  "backend": "djev_local",
  "coverage": {
    "raw": 0.84,
    "calibrated": null,
    "method": "noul_probability"
  },
  "selection": {
    "selected_id": "A",
    "probabilities": {
      "A": 0.91,
      "B": 0.06,
      "N": 0.03
    },
    "confidence_raw": 0.91,
    "confidence_calibrated": null
  },
  "candidate_quality": {},
  "diagnostics": {},
  "latency_ms": 18.2
}
```

Raw fields and calibrated fields are never silently aliased. A calibrated field remains `null` until a named calibrator has been applied.

## 13. Public response

A public response can contain:

```text
candidates
selected semantic action, if any
raw/calibrated coverage evidence
raw/calibrated selection evidence
controller meta-action + reason code
per-round trace summary
latency/usage telemetry
```

The public response must not expose provider secrets or require consumers to understand Jev/Djev-specific envelopes.
