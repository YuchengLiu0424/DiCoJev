# Local Setup and Execution Shapes

This file explains how the project is intended to be run locally. It is independent of release/version-control policy.

## 1. Base environment

Recommended:

```text
Python 3.11+
no external service for offline development, or
the separately installed LLaDA-V model/source for the final local runtime
```

Create the Python environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Unit tests must not require a model server:

```bash
pytest
```

## 2. Deployment shape A — offline deterministic development

Use:

```text
Fake/fixture CandidateGenerator
MockDecisionBackend
Threshold RiskController
Deterministic FeedbackCompiler
```

Purpose:

- schema development;
- harness tests;
- controller tests;
- CI;
- no GPU/network/API keys.

The offline example constructs these components directly. `configs/default.yaml` describes the
real v5 LLaDA-V runtime and therefore expects that service to be available.

## 3. Deployment shape B — Mercury or local DLM + conventional ranker

```text
Mercury text generator or local DiffusionGemma generator
        |
        v
CrossEncoderDecisionBackend
```

Use this as the conventional generate-then-rank baseline.

The exact cross-encoder checkpoint should be configurable; experiments must record it. Coverage must be provided by an explicit set-level method rather than silently reusing the top candidate score.

## 4. Deployment shape C — local DLM + local Djev

```text
local DiffusionGemma generator service  (for candidate generation)
        |
        v
Decision Harness
        |
        v
local Djev structured-read service      (for coverage/selection)
```

Example service addresses in repository configs:

```text
generator: http://127.0.0.1:8000
Djev:      http://127.0.0.1:8011
```

Important: this is two diffusion inference stages. If both services load their own model runtime, measure memory and latency accordingly.

Djev upstream setup evolves quickly. Follow its current repository instructions rather than copying an old engine patch recipe into this project:

https://github.com/mmastrac/djev

This topology requires a suitably provisioned accelerator host for Djev's patched vLLM stack. It
is retained as a reference comparison, not as the supported consumer-laptop path. For local runs
on the current machine, use Laya on port 8000; for hosted reads, use Jev Cloud.

## 5. Deployment shape D — local DLM + Jev Cloud

```text
local DiffusionGemma generator
        |
        v
Decision Harness
        |
        v
JevCloudBackend
```

Set credentials only in the local environment, for example:

```bash
export JEV_API_KEY="..."
```

Never commit an API key or place one in example configs.

This path is useful as a strong hosted structured-decision comparison. Network and provider latency must be measured separately from local generation.

For fast text generation, replace the local generator with `MercuryGenerator` and set
`INCEPTION_API_KEY`. Mercury and Jev are separate hosted calls and their latency/usage must be
reported separately. Native image requests remain on local DiffusionGemma.

Jev API documentation:

https://jevmodel.net/docs

## 6. Deployment shape E — unified v5 local runtime (primary)

```text
LLaDA-V Runtime (one loaded process)
  |
  +-- generate()         -> DecisionSpec
  +-- structured_read()  -> coverage + selection
```

This is the v5 default. It removes the architectural requirement for Djev and reuses one model
process for generation and structured reads. Start it with `scripts/start_llada.ps1`, validate it
with both `runtime_smoke.py --generator llada` and `native_read_smoke.py`, then run:

```powershell
python -m pip install -e ".[api]"
dicojev-api --config configs/default.yaml --host 127.0.0.1 --port 8080
```

The service is bound to localhost by default. The default threshold controller is immediately
constructible; adaptive compute requires an explicitly fitted policy supplied by application code.

### Native GUI and direct embedding

`dicojev-gui` opens the native Decision Studio and invokes `DirectClient` in-process; it does not
call the FastAPI endpoint. Other Python applications can use the same `DirectClient.from_config()`
entry point with typed `DecisionRequest` objects. The underlying LLaDA adapter still communicates
with the separately loaded model runtime configured on port 8002.

The GUI accepts multiple local attachments. Text/data/code files are added as bounded context and
images remain native. Install `.[media]` to enable local PDF, DOCX, faster-whisper speech
transcription, and video frame/audio extraction. This is preprocessing into the runtime's supported
text-and-image modalities, not a claim that LLaDA-V consumes raw audio or video tensors.

## 7. Generator choices

The v5 local default is the separately downloaded LLaDA-V checkpoint. The earlier local
DiffusionGemma comparison uses:

```text
google/diffusiongemma-26B-A4B-it
```

The hosted text profile uses Inception Mercury through its OpenAI-compatible API. Both local DLM
paths support image-text input but are slow on the measured CPU setup. Unit tests remain independent
of all real model paths.

Model page:

https://huggingface.co/google/diffusiongemma-26B-A4B-it

## 8. Expected application request flow

Regardless of backend:

```text
1. construct DecisionRequest
2. generator produces DecisionSpec
3. harness validates and normalizes candidates
4. backend estimates coverage + selection
5. controller returns meta-action + typed FeedbackBundle
6. FeedbackCompiler builds LoopContext
7. if EXPAND, return to step 2 with compiled feedback and prior candidates
8. if ACT, `AgentRuntime` crosses the execution boundary only when an allowlisted executor is attached
```

Without an executor, `ACT` is returned with execution status `not_requested`. Unknown tools are
rejected; arbitrary generated command strings are never executed.

For the real model-serving plan, see `docs/usage/MODEL_RUNTIME.md`.

## 9. Troubleshooting principles

- If candidate JSON is invalid, inspect generator/harness trace before changing backend code.
- If `q_cov` and `q_sel` are confused, consult `docs/design/DECISION_SEMANTICS.md`; do not patch thresholds to hide the issue.
- If Djev labels fail tokenization, fix backend label compilation; do not rewrite candidate semantics.
- If multimodal support is unavailable for a backend, report a capability mismatch or run an explicitly named text/caption baseline.
- If a model service is unavailable, fail closed rather than returning ACT from stale/default scores.


## Windows PowerShell base environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```
