# Coding Agent: Start Here

You are implementing this repository, not redesigning its research story.

## 1. Read order

Before writing code, read exactly these sources in order:

1. `docs/README.md` — learn which document owns each concept.
2. `docs/governance/VERSION_CONTROL.md` — identify the active milestone and its allowed scope.
3. `docs/design/ARCHITECTURE.md` — understand component boundaries.
4. `docs/design/DECISION_SEMANTICS.md` — understand coverage/selection/NOTA/controller invariants.
5. `docs/design/BACKENDS.md` and/or `docs/design/HARNESS.md` if the active task touches those components.
6. the matching `agents/tasks/vN.md` — execute the implementation checklist for the active milestone.
7. `agents/EXECUTION_PROTOCOL.md` — follow testing, status, and handoff rules.

Do **not** use the root README as an implementation specification. It is a public project overview.

## 2. Source-of-truth rule

Agent files do not define research semantics or release scope. If an agent task appears to conflict with a human-owned authoritative doc, stop the conflicting implementation and follow the human-owned doc.

Authority order:

```text
docs/governance/VERSION_CONTROL.md   -> milestone scope

docs/design/*                        -> technical contracts

docs/research/*                      -> research claims/evaluation framing

docs/usage/*                         -> operator-facing setup

agents/*                              -> execution instructions only
```

## 3. Scope rule

Implement one active milestone only. Do not pull a later feature forward because it is convenient or interesting. If a new idea is outside the declared plan, record it as a v6+ note rather than changing the current architecture.

## 4. Non-negotiable implementation invariants

- Jev/Djev wire schemas stay inside adapters/compilers.
- `DecisionSpec` remains backend-neutral.
- `q_cov` and `q_sel` remain distinct.
- NOTA remains distinct from ABSTAIN/EXPAND/ESCALATE.
- `DjevLocalBackend` is measured as a separate diffusion read after DLM generation.
- unit tests require no GPU/network/key.
- raw and calibrated scores remain separate.
- images are not logged by default.
- unsupported multimodal capability must be explicit; never silently call caption-only processing “native multimodal”.
- failures that invalidate decision evidence must fail closed rather than default to ACT.
