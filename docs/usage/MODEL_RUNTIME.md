# Supported DLM Runtime Paths

This document owns real candidate-generator setup. The project no longer plans or requires a
separate rented GPU server. Supported v2 paths are the hosted Mercury API for fast text decisions
and the proven local DiffusionGemma runtime for text or native-image decisions.

## Runtime choice

```text
fast hosted text path:  Inception Mercury API
local/private path:     google/diffusiongemma-26B-A4B-it
native image path:      local DiffusionGemma
```

Mercury is treated as text-only until Inception publishes and the project verifies a native image
request contract. Image requests must fail explicitly on Mercury; they are never silently captioned.

## Mercury API

Set the API key only in the environment:

```bash
export INCEPTION_API_KEY="..."
python scripts/runtime_smoke.py --generator mercury
```

The default endpoint is `https://api.inceptionlabs.ai/v1` and the default stable model identifier is
`mercury-2.5`; both can be overridden with `INCEPTION_BASE_URL` and `INCEPTION_MODEL`. Mercury uses
the same bounded project-native candidate parser as the local generator. It can return optional
`tool` and exact `constraint_violations` metadata for each candidate.

## Local DiffusionGemma

## Model storage

Weights must be downloaded into a model cache such as Hugging Face cache or a configured data volume. Never commit model weights to Git.

Suggested ignored locations/patterns include `models/`, `weights/`, `checkpoints/`, `*.safetensors`, `*.bin`, `*.pt`, and `*.pth`.

Run the already-proven local quantized DiffusionGemma setup through its OpenAI-compatible local
endpoint. CPU inference is slow but functional and keeps model data local. After starting that
runtime, check it with:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
curl --fail http://127.0.0.1:8000/v1/models
python scripts/runtime_smoke.py --generator local --base-url http://127.0.0.1:8000
```

`runtime_smoke.py` performs the health check, one text candidate generation, then one
`MISSING_ACTION` typed-feedback expansion. It fails if output is not a bounded project-native
`DecisionSpec`, repeats a prior candidate exactly, or exceeds the candidate budget.

For an end-to-end text decision with local Djev:

```bash
# Start Djev separately by following https://github.com/mmastrac/djev
# Its System One endpoint is expected at port 8011.
python examples/real_text_decision.py --backend djev
```

For Jev Cloud, set `JEV_API_KEY` only in the environment and run the example with
`--backend jev`. The application records generation, backend-read, and feedback-compilation
latencies separately. DiffusionGemma generation plus Djev is explicitly a two-diffusion-stage
topology.

The official Jev API root is `https://api.typesafe.ai`. Override it with `JEV_BASE_URL` only
for an intentionally compatible service.

## Local Laya comparison

Laya is an open-weight System One comparison backend with a Jev-compatible HTTP endpoint. It
is not Jev or Djev, and DiCoJev records it as `laya_local`.

On Windows, install it in the application environment and run the English checkpoint on CPU:

```powershell
.\.venv\Scripts\python.exe -m pip install "laya[serve]"
$env:LAYA_DEVICE = "cpu"
$env:LAYA_MODELS = "english"
$env:LAYA_PORT = "8011"
.\.venv\Scripts\laya-serve.exe
```

The first launch downloads the checkpoint to the Hugging Face cache. In another terminal:

```powershell
.\.venv\Scripts\python.exe scripts/live_backend_smoke.py --backend laya
.\.venv\Scripts\python.exe examples/real_text_decision.py `
  --backend laya `
  --generator-url http://127.0.0.1:11434 `
  --generator-model dicojev-diffusiongemma
```

Laya confidence is not numerically interchangeable with Jev confidence, so backend-specific
threshold calibration is required before comparing controller behavior.

The client interface and telemetry contract remain stable if the serving engine changes.

## Measured personal-computer trial

A CPU-only Windows/WSL trial was completed on 2026-09-27 with the 25.3B-parameter
DiffusionGemma Q4_K_M GGUF. It used the dedicated `llama.cpp` DiffusionGemma branch rather
than substituting an autoregressive local model. The host has 64 GB RAM and an 8 GB RTX 4070
Laptop GPU; the WSL runtime was limited to 31 GiB RAM plus 8 GiB swap and the test deliberately
used CPU inference.

The model ran successfully with zero swap use. One 256-token canvas took 5m19s wall time and
peaked at about 27.8 GiB RSS. A two-block 512-token run took 7m27s at about 1.5 effective
tokens/second with the same peak RSS. See `docs/research/LOCAL_DLM_TRIAL.md` for the exact
configuration, decision-backend results, and current strict-JSON limitation.

This establishes the local proof path. External GPU serving is abandoned; performance-sensitive
text runs use Mercury, while native-image or local/private runs accept the measured CPU latency.

## Djev

Djev is a separate reference backend service, not the canonical DiCoJev runtime. When DiffusionGemma generation and Djev structured read are both used, report two diffusion stages and the memory/latency of each.
