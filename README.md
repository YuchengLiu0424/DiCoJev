# DiCoJev

**DiCoJev** is a local-first research framework for **coverage-aware Jev-style decision making over diffusion-generated action sets**.

Current implementation: **1.2.0**. The published 1.0.0 research release is extended
with a native desktop interface, direct Python client, and experimental local media intake. The
offline path needs no model, network access, or API key; real model and hosted-backend checks are
explicitly opt-in.

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

DiCoJev always keeps the core route as a **diffusion language model + decision model** pair.
When encrypted Mercury and Jev credentials are registered, new desktop chats default to
**Mercury Cloud + Jev Cloud**, the tested fast executable route. Mercury also performs intent
drafting for those chats. Without both credentials, new
chats retain the private **LLaDA Local + LLaDA Native Decision** route on port 8002; it requires
the local service and is slow on CPU-only machines. Qwen2 on Ollama port 11434 is only the fast
local intent bridge for LLaDA chats, structuring context-only input before the core decision loop; it never
replaces the diffusion generator or final decision reader. DiffusionGemma remains available in the registry for a compatible vLLM,
Transformers, SGLang, or custom llama.cpp runtime; stock Ollama on the tested host rejects its
architecture. Laya remains an optional local System One decision adapter on port 8000.
The legacy unified LLaDA-V research path remains documented under `configs/versions/`; supported
application defaults live in `configs/default.yaml`. The default controller is the
deterministic threshold policy; the learned adaptive policy remains an explicit experiment because
the recorded pre-1.0 study did not show it outperforming fixed policies.

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
python examples/offline_agent.py
python -m pytest
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,api]"
python examples/offline_agent.py
python -m pytest
```

The demo returns an `ACT` response whose `execution_trace` records an allowlisted `record` tool
changing `approved` from `false` to `true`. CI reports the current test count; six live-service
checks are opt-in and skip when their external runtimes are not enabled.

## Native desktop interface

Install the project and open the non-browser Decision Studio:

```powershell
python -m pip install -e "."
dicojev-gui
```

The GUI calls the Python runtime directly—there is no FastAPI/JSON hop. It accepts context, goal,
tools, constraints, structured state, and attachments, then displays the controller action,
selected candidate, coverage, confidence, feedback, candidates, and trace. The selected language
and decision model services must be running for real inference.

Paste a full request, context only, or fill a few fields and choose **Complete missing fields**.
**Make decision** also drafts incomplete inputs before running the decision loop; review the draft
and click it again to continue. The configured DLM fills missing goal, instructions, boundaries,
and task-relevant options while preserving supplied fields. Tasks are not forced into a
"safest next action" template. Generated instructions/options appear in history and are supplied
to the candidate generator. Optional tools and constraints may remain empty; review proposed
tools before proceeding. If the DLM is unavailable, inputs stay intact and no interpretation is
fabricated. Infrastructure failures are displayed as **UNAVAILABLE**, not as evidence-based
`ESCALATE` decisions. Arithmetic follows the same DLM-backed completion flow as other tasks.
Multiple chats and bounded recent history are kept in a private local SQLite database. Choose
**Open data folder** to inspect it; launch with `--account NAME` for another local profile or
`--data-dir PATH` to choose its location.

The sidebar treats projects as containers, with their chats shown as indented children. **No project**
is a separate container for standalone chats. Use ＋ to create projects or numbered chats
(`Chat 1`, `Chat 2`, …); right-click a chat to rename, move it to a project/No project, or delete it.
Project deletion removes its chats and leaves the folder's files untouched.
The rightmost conversation column shows structured user requests right-aligned and DiCoJev
coverage/adequacy, option scores, and choices left-aligned. **Settings** opens inside the same window.
The optional Structured State JSON is combined with the ordinary context, constraints, generated
candidate set, and decision instructions; it is not the complete or exclusive Jev input.
The three workspace sections have draggable horizontal dividers, so navigation, request, and
conversation width can be traded off directly. Vertical scrollbar tracks stay hidden; the mouse
wheel and touchpad continue scrolling the section under the pointer.
Its dark Model registry tab adds models by name, radio-button role (language/decision) and
deployment (local/cloud). Local and cloud are exclusive sources: local shows a folder picker;
cloud shows endpoint, model identifier, and API key controls. It also records the
adapter, endpoint, and optional provider model identifier. Right-click a registered model to edit
its details or credentials. The Project chats tab sets each chat's name and independent language
and decision models using only registered choices. Each chat keeps its own pair. Full
**Language model** and **Decision model** selectors in the workspace switch the
current chat immediately, without changing other chats. Local models use an adapter-specific loopback runtime default;
weights are loaded by that server. **Choose model folder** discovers metadata and weight files
in the selected folder or immediate subfolders; it rejects missing, ambiguous, or mismatched
model types. Discovery does not start a runtime or prove the weights can load. Generic decision
models need a `dicojev-model.json` file alongside their weights, for example:

```json
{"role":"decision","adapter":"laya_local","model_identifier":"english","endpoint":"http://127.0.0.1:8000"}
```

Cloud registration asks permission for a small, potentially billable capability test using the
endpoint, model identifier, and key. A key alone cannot reveal model type. Rejected credentials,
unreachable services, and incompatible language/decision responses are reported separately.
Settings stores per-model keys using Windows DPAPI and
reports provider-supplied input, output, and total tokens grouped by model and chat. A zero means
the model server did not report token counts; DiCoJev does not invent them.

Projects optionally bind chats to a selected local folder. The project browser can add selected
files to the multimodal request, and the public `ProjectWorkspace` API provides path-confined,
read-only access by default. `ProjectAgentTools` supplies allowlist-ready list/read/write handlers,
and `ComputerUseAdapter` defines the boundary for an explicitly installed desktop provider. This
is not unrestricted computer control: writes require explicit opt-in, shell execution is not
exposed, and desktop automation is not silently enabled.

For a convenient Windows desktop launcher after installation:

```powershell
.\scripts\install_windows_shortcut.ps1
```

This places the user-facing launcher at `DiCoJev App\DiCoJev.exe` and points the desktop shortcut
there. The managed `.venv` remains the runtime behind the launcher and should not be deleted.

On Windows the desktop enables per-monitor-v2 DPI awareness before creating the window, uses
monitor-calibrated text scaling, and provides example placeholders that clear when each field is
used. Its diffusion-to-decision diamond mark is installed as the window/taskbar icon at multiple
resolutions.

Images and plain-text/code/data files work with the base installation. Experimental PDF, DOCX,
speech, and video intake use optional local preprocessors:

For a text-only pair such as Mercury + Jev, image and sampled-video frames are first analyzed by
the local Ollama model `qwen3.5:9b`; the bounded, explicitly labeled vision evidence then enters the
normal DLM-to-decision loop. A model pair that declares native multimodal support continues to
receive the original pixels directly. DiCoJev fails clearly if the required local vision model is
not installed or running rather than silently ignoring an attachment. When either downstream model
is cloud-hosted, the desktop asks permission before sending the locally derived text description;
the original image bytes remain local.

```powershell
python -m pip install -e ".[media]"
```

Speech is transcribed locally with faster-whisper. Video is sampled into image frames and its audio
is transcribed. The first speech run may download the configured Whisper checkpoint; set
`DICOJEV_WHISPER_MODEL` to choose another local model identifier. Files are converted into the
text-and-image state supported by the selected model and never silently ignored. Laya currently
declares text-only input; image-bearing requests require a decision backend that declares image support.

Test attachment preprocessing independently of the model:

```powershell
python scripts\media_intake_smoke.py recording.wav notes.pdf clip.mp4 --speech-model tiny
```

For direct use inside another Python program:

```python
from dicojev import DecisionRequest, DirectClient
from dicojev.cli import PACKAGED_DEFAULT_CONFIG
from dicojev.schemas import MultimodalState

client = DirectClient.from_config(PACKAGED_DEFAULT_CONFIG)
response = client.decide_sync(
    DecisionRequest(
        state=MultimodalState(text="The customer reports two charges."),
        goal="Choose the safest next action",
        available_tools=("inspect_transactions", "escalate_to_human"),
    )
)
print(response.action, response.selected_candidate)
```

The optional API extra exposes the same runtime at `POST /v1/decide` and returns the full typed
feedback and execution trace. To run the unified local LLaDA path, start the separately installed LLaDA-V
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
or latency advantage. Read the historical [1.0 release evaluation](docs/research/V5_EVALUATION.md)
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

## License

DiCoJev is licensed under the [Apache License 2.0](LICENSE).
