# DiCoJev

**DiCoJev** is a local-first research framework for **coverage-aware Jev-style decision making over diffusion-generated action sets**.

Current implementation: **v5 / 1.0.0 release candidate**. It is a research runtime for agents that
must choose from an action set they generated themselves. The offline release path needs no model,
network access, or API key; real model and hosted-backend checks are explicitly opt-in.

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

The v5 default is the unified local **LLaDA-V** adapter on port 8002. One loaded model service
handles multimodal candidate generation and native structured reads. The default controller is the
deterministic threshold policy; the learned adaptive policy remains an explicit experiment because
the live v4 study did not show it outperforming fixed policies.

Mercury, DiffusionGemma, Jev, Djev, Laya, and the cross-encoder remain supported comparison paths.
They are not prerequisites for offline development. The earlier external GPU-server plan has been
abandoned.

## Decision backends

| Backend | Role |
|---|---|
| `MockDecisionBackend` | deterministic tests and offline development |
| `JevCloudBackend` | hosted structured-decision reference |
| `DjevLocalBackend` | local Jev-compatible diffusion structured-read reference |
| `LayaLocalBackend` | local open-weight Jev-compatible System One comparison |
| `CrossEncoderDecisionBackend` | conventional generate-then-rank baseline |
| `NativeDLMDecisionBackend` | project-owned diffusion structured-read path |

When a DiffusionGemma generator is followed by `DjevLocalBackend`, the system performs **two diffusion inference stages**. That topology is a reference baseline. The target native path allows one project-controlled DLM runtime to expose both `generate()` and `structured_read()` modes.

## Five-minute offline workflow

Requirements: Python 3.11 or newer. This path is deterministic and downloads no model.

For Linux or macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,api]'
python examples/v5_offline_agent.py
python -m pytest
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,api]"
python examples/v5_offline_agent.py
python -m pytest
```

The demo returns an `ACT` response whose `execution_trace` records an allowlisted `record` tool
changing `approved` from `false` to `true`. The suite currently has **117 passing tests** and six
skipped opt-in service tests.

The optional API extra exposes the same runtime at `POST /v1/decide` and returns the full typed
feedback and execution trace. To run the real v5 path, start the separately installed LLaDA-V
service, validate generation and native reads, then start the API:

```powershell
.\scripts\start_llada.ps1 `
  -Python 'D:\LLM\LLaDA-V\.venv\Scripts\python.exe' `
  -ModelPath 'D:\LLM\LLaDA-V' `
  -CodePath 'D:\LLM\LLaDA-V-code'

.\.venv\Scripts\python.exe scripts\runtime_smoke.py --generator llada --timeout 600
.\.venv\Scripts\python.exe scripts\native_read_smoke.py --base-url http://127.0.0.1:8002
dicojev-api --config configs/default.yaml --host 127.0.0.1 --port 8080
```

Model weights and the official LLaDA-V source are not bundled. On the measured CPU setup, local
inference works but can take minutes. Without an injected `AllowlistedToolExecutor`, an `ACT` is
reported as `not_requested`; generated text is never treated as an arbitrary shell command.

See [`docs/usage/LOCAL_SETUP.md`](docs/usage/LOCAL_SETUP.md) for deployment shapes and [`docs/usage/MODEL_RUNTIME.md`](docs/usage/MODEL_RUNTIME.md) for the real DLM serving plan.

## Evidence and honest limits

| Question | Current evidence | Conclusion |
|---|---|---|
| Does the closed loop handle controlled failures? | 11/11 cases | Yes, including all four controller actions and a native-image case. |
| Does deleting the acceptable action lower coverage? | Matched live Jev deletion | Yes in the recorded cases. |
| Is local LLaDA repeatable? | Five fixed local reads | Yes under the recorded configuration. |
| Is typed feedback better than binary or long-form feedback? | Five-task live study | Not demonstrated. |
| Does learned adaptive compute beat fixed compute? | Same live study | Not demonstrated; it is not the default. |
| Is native LLaDA coverage as strong as hosted Jev? | Six matched sets | No; it was weaker in this small study. |

These results validate the software architecture and measurement pipeline, not a general accuracy
or latency advantage. Read [`docs/research/V5_EVALUATION.md`](docs/research/V5_EVALUATION.md)
before citing results.

## Relationship to current agent frameworks

DiCoJev is narrower than a general agent framework and can be embedded inside one of their decision
nodes. This comparison is about scope, not overall superiority.

| Project | Primary strength | DiCoJev's distinct focus | Prefer the other project when... |
|---|---|---|---|
| [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) | durable stateful graphs and human-in-the-loop workflows | adequacy of a dynamically generated candidate set | you need persistence, checkpointing, or general workflow orchestration |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | multi-agent orchestration and broad integrations | a small, measurable single-decision control plane | you need multi-agent collaboration or an enterprise ecosystem |
| [Hugging Face smolagents](https://huggingface.co/docs/smolagents/index) | lightweight code/tool agents and model integrations | fail-closed selection over alternatives before execution | you want a general tool or code agent |
| [Jev](https://jevmodel.net/docs) / [Djev](https://github.com/mmastrac/djev) | structured decisions over supplied choices | generated-choice coverage and feedback-controlled retries | your choice set is already complete |

DiCoJev's specific advantages are separate `q_cov` and `q_sel`, observable forced-choice failure,
bounded typed feedback, backend-neutral evidence, reproducible candidate-corruption tests, and an
allowlisted execution boundary. It does not replace framework-level memory, distributed execution,
connectors, sandboxed code execution, or production observability.

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
