# Coding Agent: Start Here

You are implementing **DiCoJev**, not redesigning its research story.

## Read order

Before writing code, read in this order:

1. `docs/README.md` — document ownership.
2. `docs/governance/VERSION_CONTROL.md` — active milestone and allowed scope.
3. `docs/design/ARCHITECTURE.md` — component boundaries.
4. `docs/design/DECISION_SEMANTICS.md` — coverage/selection/NOTA/controller invariants.
5. `docs/design/FEEDBACK_PROTOCOL.md` — typed feedback and loop invariants.
6. `docs/design/BACKENDS.md` and/or `docs/design/HARNESS.md` as required.
7. matching `agents/tasks/vN.md` — implementation checklist.
8. `agents/EXECUTION_PROTOCOL.md` — testing and handoff rules.

Do not use the root README as an implementation specification.

## Authority order

```text
docs/governance/VERSION_CONTROL.md -> milestone scope
docs/design/*                      -> technical contracts
docs/research/*                    -> research/evaluation claims
docs/usage/*                       -> operator setup
agents/*                            -> execution instructions only
```

## Scope rule

Implement one active milestone only. Do not pull later-version features forward unless required by a current invariant or bug/interface correction.

## Non-negotiable invariants

- `DecisionSpec` stays backend-neutral.
- Jev/Djev wire schemas stay inside adapters/compilers.
- `q_cov` and `q_sel` remain distinct.
- candidate quality remains distinct from both.
- NOTA remains distinct from controller meta-actions.
- feedback is typed and bounded; it is not free-form chain-of-thought.
- feedback is not a fourth Jev schema component.
- `FeedbackCompiler` does not decide whether to EXPAND; the controller does.
- DLM + Djev is measured as two diffusion stages.
- raw/calibrated scores remain separate.
- unit tests require no GPU/network/key.
- unsupported multimodal capability is explicit.
- evidence/infrastructure failures fail closed.
