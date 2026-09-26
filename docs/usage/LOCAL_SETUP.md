# Local Setup and Execution Shapes

This file explains how the project is intended to be run locally. It is independent of release/version-control policy.

## 1. Base environment

Recommended:

```text
Python 3.11+
Linux for GPU/model-serving work
NVIDIA GPU for the default 26B DLM path
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

The default configuration is intentionally compatible with this mode.

## 3. Deployment shape B — local DLM + conventional ranker

```text
local DiffusionGemma generator
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

Jev API documentation:

https://jevmodel.net/docs

## 6. Deployment shape E — native project DLM read

```text
Project DLM Runtime
  |
  +-- generate()         -> DecisionSpec
  +-- structured_read()  -> coverage + selection
```

This path removes the architectural requirement for a Djev service. The first implementation may use separate passes through one runtime; later optimizations may share weights, multimodal preprocessing, or other state when correctness is preserved.

## 7. Default model

The default candidate generator is:

```text
google/diffusiongemma-26B-A4B-it
```

Current model references describe image-text-to-text usage and vLLM/Transformers serving. Model checkpoint size and GPU requirements are significant, so the repository must keep fake/small test paths independent of the full checkpoint.

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
8. if ACT, caller executes the semantic action
```

The decision system does not silently execute tools unless the caller has explicitly connected an execution layer.

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
Copy-Item .env.example .env
pytest
```
