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

## v1 runtime deliverable

v1 must document and test a fresh-machine sequence for:

```text
GPU/runtime prerequisite check
-> model-serving environment installation
-> model cache/download
-> server launch
-> health/readiness check
-> one text candidate-generation smoke test
-> one feedback-guided expansion smoke test
```

The exact serving engine may evolve with DiffusionGemma support. The client interface and telemetry contract must remain stable even if the serving implementation changes.

## Djev

Djev is a separate reference backend service, not the canonical DiCoJev runtime. When DiffusionGemma generation and Djev structured read are both used, report two diffusion stages and the memory/latency of each.
