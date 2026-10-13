# Supported DLM Runtime Paths

This document owns real candidate-generator setup. The project no longer plans or requires a
separate rented GPU server. The v5 primary path is one local LLaDA-V process for generation and
native structured reads. Mercury, DiffusionGemma, Jev, Djev, and Laya are comparison paths.

## Runtime choice

```text
final local path:       LLaDA-V generation + structured reads on port 8002
fast hosted text path:  Inception Mercury API
legacy local baseline:  google/diffusiongemma-26B-A4B-it
hosted verifier:        Jev Cloud
```

Mercury is treated as text-only until Inception publishes and the project verifies a native image
request contract. Image requests must fail explicitly on Mercury; they are never silently captioned.

## Unified LLaDA-V runtime

The model checkpoint and official source checkout are installed separately and are never committed
to this repository. On Windows, start the server with explicit paths:

```powershell
.\scripts\start_llada.ps1 `
  -Python 'D:\LLM\LLaDA-V\.venv\Scripts\python.exe' `
  -ModelPath 'D:\LLM\LLaDA-V' `
  -CodePath 'D:\LLM\LLaDA-V-code'
```

The server exposes OpenAI-compatible generation plus `/v1/structured-read` and
`/v1/structured-read-batch`. Generation and reads share the loaded weights and bounded projected
vision-feature cache. The batch read path is disabled by default because it was slower than cached
sequential reads on the measured CPU host.

Verify both contracts before starting DiCoJev's API:

```powershell
.\.venv\Scripts\python.exe scripts\runtime_smoke.py --generator llada --timeout 600
.\.venv\Scripts\python.exe scripts\native_read_smoke.py --base-url http://127.0.0.1:8002
dicojev-api --config configs/default.yaml --host 127.0.0.1 --port 8080
```

Ollama does not implement the required LLaDA-V masked structured-read contract. The supported
server is `scripts/llada_openai_server.py` using the official model code.

## Mercury API

In the native desktop, open **Settings** and save the API key for the active model. It is encrypted
with Windows DPAPI for the current user and is not written to configuration or environment
variables. For headless/legacy generator use, the environment remains a compatibility option:

```bash
export INCEPTION_API_KEY="..."
python scripts/runtime_smoke.py --generator mercury --output results/v2_mercury_smoke.json
```

The default endpoint is `https://api.inceptionlabs.ai/v1` and the default stable model identifier is
`mercury-2.5`; both can be overridden with `INCEPTION_BASE_URL` and `INCEPTION_MODEL`. Mercury uses
the same bounded project-native candidate parser as the local generator. It can return optional
`tool` and exact `constraint_violations` metadata for each candidate.
`MERCURY_API_KEY` is accepted as an alias for `INCEPTION_API_KEY`.
If Mercury overproduces candidates, its adapter deterministically retains the first requested
items; it never exceeds the request/expansion candidate budget.

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
$env:LAYA_PORT = "8000"
.\.venv\Scripts\laya-serve.exe
```

Port 8000 is Laya's current default. Set both `LAYA_PORT` on the server and
`DICOJEV_LAYA_URL`/`--laya-url` on the client if you intentionally choose another port.

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

Djev is a separate accelerator-oriented reference backend service, not the canonical DiCoJev
runtime. Its patched vLLM/DiffusionGemma stack is not supported by Ollama and is not a practical
deployment on the project's consumer laptop GPU. Keep `DjevLocalBackend` for reproducible
comparison with a suitably provisioned external service; use hosted Jev or local CPU Laya for
working decision reads on this machine.

When DiffusionGemma generation and Djev structured read are both used, report two diffusion
stages and the memory/latency of each. Do not treat an unavailable Djev service as a failure of the
DiCoJev controller or silently substitute Laya results under the `djev_local` backend name.
