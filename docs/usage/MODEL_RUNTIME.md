# Real DLM Runtime Plan

This document owns the planned local runtime shape for real model integration. It does not make GPU/model serving a v0 dependency.

## Default model

```text
google/diffusiongemma-26B-A4B-it
```

## Separation of environments

Recommended topology:

```text
DiCoJev application environment
        |
        | HTTP/local client protocol
        v
separate GPU model-serving environment
        |
        v
DiffusionGemma runtime
```

This keeps CUDA/vLLM/model dependencies from contaminating CPU-only unit tests.

## Model storage

Weights must be downloaded into a model cache such as Hugging Face cache or a configured data volume. Never commit model weights to Git.

Suggested ignored locations/patterns include `models/`, `weights/`, `checkpoints/`, `*.safetensors`, `*.bin`, `*.pt`, and `*.pth`.

## v1 fresh-machine runtime sequence

The application and GPU server should use separate environments. On a Linux NVIDIA host:

```bash
nvidia-smi
docker --version
mkdir -p "$HOME/.cache/huggingface"
docker run --gpus all --rm --shm-size 32g --ipc=host \
  -p 8000:8000 \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -e HF_TOKEN \
  lmsysorg/sglang:latest \
  python3 -m sglang.launch_server \
  --model-path google/diffusiongemma-26B-A4B-it \
  --host 0.0.0.0 --port 8000
```

The first launch downloads weights into the mounted Hugging Face cache. Gemma access may
require accepting its license and setting `HF_TOKEN`; never place that token in repository
files. The model is large and requires an appropriate supported GPU/runtime. DiffusionGemma
serving support evolves, so verify the current model card's SGLang/vLLM notes before launch.

In the CPU application environment, install and check readiness:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
curl --fail http://127.0.0.1:8000/v1/models
python scripts/runtime_smoke.py --base-url http://127.0.0.1:8000
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

This establishes that external GPU rental is not required for the project's proof path.
GPU serving remains useful for iteration speed, but is an optimization rather than a basic
installation requirement.

## Djev

Djev is a separate reference backend service, not the canonical DiCoJev runtime. When DiffusionGemma generation and Djev structured read are both used, report two diffusion stages and the memory/latency of each.
