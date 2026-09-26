# DiCoJev

**DiCoJev** is a local-first research framework for **coverage-aware Jev-style decision making over diffusion-generated action sets**.

It targets fast multimodal agents whose valid next action is not known in advance. A diffusion language model (DLM) proposes candidate actions; a structured decision backend evaluates both **whether the candidate set is adequate** and **which candidate is best**; a typed low-bandwidth feedback loop then decides whether to act, expand the action set, abstain, or escalate.

```text
Multimodal state + goal + tools + constraints
                     |
                     v
             DLM CandidateGenerator
                     |
                     v
                 DecisionSpec
                     |
                     v
                DecisionHarness
             /                    \
            v                      v
    DecisionBackend          Candidate Manager
     coverage + selection          |
            |                       |
            v                       |
       RiskController              |
            |                       |
     meta-action + feedback         |
            |                       |
            v                       |
       FeedbackCompiler ------------+
            |
            +--> ACT
            +--> EXPAND --> DLM CandidateGenerator
            +--> ABSTAIN
            +--> ESCALATE
```

## Why DiCoJev

Structured decision systems such as Jev-style selectors are efficient because they answer compact questions over supplied choices. Their key assumption is usually closed-world: the relevant choices are already present.

Generated action sets break that assumption. A selector can assign 0.95 confidence to candidate `A` while the actually acceptable action is absent from the set. DiCoJev therefore keeps two quantities separate:

```text
q_cov = evidence that the current candidate set contains at least one acceptable action
q_sel = evidence/confidence for the selected action conditional on the current set
```

When the set is inadequate, DiCoJev does not force a top-1 action. It emits a compact typed feedback signal such as `MISSING_ACTION` or `TOOL_MISMATCH`, and the controller can request another generation round without requiring long-form natural-language deliberation.

## Core project contributions

DiCoJev is designed around four coupled ideas:

1. **Diffusion-generated action sets** — a multimodal DLM constructs semantic candidate actions rather than requiring callers to predefine all choices.
2. **Explicit candidate-set coverage** — candidate-set adequacy is modeled separately from within-set selection confidence.
3. **Typed low-bandwidth feedback** — structured evidence is compressed into small feedback codes that drive targeted regeneration, abstention, or escalation.
4. **Backend-neutral structured decision** — Jev, Djev, cross-encoders, and a project-owned native DLM read path are interchangeable behind one `DecisionBackend` contract.

The project does **not** claim that candidate generation, generate-then-rank, NOTA, conformal coverage, or feedback loops are individually new. The research question is whether these components can be combined into a fast multimodal decision architecture whose uncertainty about its **self-generated decision space** is explicit and actionable.

## Default model and deployment philosophy

The default candidate generator family is:

```text
google/diffusiongemma-26B-A4B-it
```

The project is **local-first**. Model-serving and GPU dependencies are kept outside the CPU-only unit-test path. Hosted Jev is an optional comparison backend, not a required dependency.

## Decision backends

| Backend | Role |
|---|---|
| `MockDecisionBackend` | deterministic tests and offline development |
| `JevCloudBackend` | hosted structured-decision reference |
| `DjevLocalBackend` | local Jev-compatible diffusion structured-read reference |
| `CrossEncoderDecisionBackend` | conventional generate-then-rank baseline |
| `NativeDLMDecisionBackend` | project-owned diffusion structured-read path |

When a DiffusionGemma generator is followed by `DjevLocalBackend`, the system performs **two diffusion inference stages**. That topology is a reference baseline. The target native path allows one project-controlled DLM runtime to expose both `generate()` and `structured_read()` modes.

## Local workflow

For CPU-only development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

The offline path uses a fake generator, mock backend, deterministic feedback compiler, and threshold controller. Real DiffusionGemma/Djev/Jev integrations are activated by later runtime profiles and do not belong in unit-test prerequisites.

See [`docs/usage/LOCAL_SETUP.md`](docs/usage/LOCAL_SETUP.md) for deployment shapes and [`docs/usage/MODEL_RUNTIME.md`](docs/usage/MODEL_RUNTIME.md) for the real DLM serving plan.

## How to read this repository

Different documents have different owners and audiences:

- **Project overview / local entry point:** this `README.md`
- **Research thesis, applications, strengths, limitations, contributions:** [`docs/research/PROJECT_DESCRIPTION.md`](docs/research/PROJECT_DESCRIPTION.md)
- **Prior work and novelty boundaries:** [`docs/research/RELATED_WORK.md`](docs/research/RELATED_WORK.md)
- **System component contracts:** [`docs/design/ARCHITECTURE.md`](docs/design/ARCHITECTURE.md)
- **Coverage / selection / NOTA / controller semantics:** [`docs/design/DECISION_SEMANTICS.md`](docs/design/DECISION_SEMANTICS.md)
- **Typed feedback protocol:** [`docs/design/FEEDBACK_PROTOCOL.md`](docs/design/FEEDBACK_PROTOCOL.md)
- **Harness transformation rules:** [`docs/design/HARNESS.md`](docs/design/HARNESS.md)
- **Version and release scope:** [`docs/governance/VERSION_CONTROL.md`](docs/governance/VERSION_CONTROL.md)
- **Coding-agent entry point:** [`agents/START_HERE.md`](agents/START_HERE.md)

The complete document ownership map is in [`docs/README.md`](docs/README.md).

## Repository layout

```text
DiCoJev/
├── README.md
├── pyproject.toml
├── configs/
├── docs/
│   ├── README.md
│   ├── research/
│   ├── design/
│   ├── usage/
│   ├── governance/
│   └── reference/
├── agents/
│   ├── START_HERE.md
│   ├── EXECUTION_PROTOCOL.md
│   └── tasks/
├── src/dicojev/
├── tests/
├── benchmarks/
├── examples/
├── scripts/
└── .github/
```

## Jev-compatible decision read

For Jev-compatible backends, DiCoJev compiles coverage and selection into ordinary structured questions rather than changing the Jev wire model:

```text
coverage  -> noul
selection -> choice
```

Typed feedback is **not** a fourth Jev field. Backend evidence is normalized first; the project-owned controller and `FeedbackCompiler` then produce the next-loop feedback signal.

For the full research framing, start with [`docs/research/PROJECT_DESCRIPTION.md`](docs/research/PROJECT_DESCRIPTION.md).
