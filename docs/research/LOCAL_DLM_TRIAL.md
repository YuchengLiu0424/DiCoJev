# Local DiffusionGemma + Jev/Laya Trial

Date: 2026-09-27

## Purpose

Test the project's intended composition on a normal personal computer without replacing the
diffusion language model with a conventional local LLM:

```text
DiffusionGemma candidate generation
              |
              +--> hosted Jev structured decision
              |
              +--> local Laya structured decision
```

Both decision backends received the same persisted candidate identifiers and actions.

## Runtime

- Host memory: 64 GB
- GPU: NVIDIA RTX 4070 Laptop GPU, 8 GB VRAM (not used for this trial)
- Linux runtime: Ubuntu 26.04 under WSL, limited to 31 GiB RAM and 8 GiB swap
- Runner: `llama.cpp` DiffusionGemma PR 24423, commit
  `3dac51dc80b1400929266453c6ced6748ccf6862`, compiled CPU-only
- Model: `diffusiongemma-26B-A4B-it-Q4_K_M.gguf`
- GGUF size: 16,806,810,208 bytes
- Decode: 256-token canvas, entropy-bound decoder, at most 48 steps, prompt KV cache enabled,
  22 CPU threads

Ollama 0.34.2 could import the GGUF and identify the `diffusion-gemma` architecture, but its
bundled runner failed to load that architecture. The dedicated development runner was therefore
used. This is a runtime-support distinction, not a model-memory failure.

## Generation measurements

| Output budget | Resolved steps | Wall time | Peak RSS | Swap | Effective throughput |
|---:|---:|---:|---:|---:|---:|
| 256 tokens / 1 block | 16 | 5m18.88s | 29,120,056 KiB (~27.8 GiB) | 0 | 1.3 tok/s |
| 512 tokens / 2 blocks | 30 | 7m26.62s | 29,120,368 KiB (~27.8 GiB) | 0 | 1.5 tok/s |

The 512-token output completed a structured thought-channel representation of every required
field and generated these candidate actions:

1. `verify_recipients`
2. `save_draft_for_review`
3. `prompt_user_for_verification`

It then repeated the answer as fenced JSON, but the second block ended partway through that
duplicate object. The production `DiffusionGemmaGenerator` correctly rejects this as malformed
instead of silently repairing semantic content. For this one-off integration trial only, the
already-completed field values were copied exactly from the model output into a persisted
`DecisionSpec`; no candidate was added or rewritten.

## Decision results

| Backend | Selected | Coverage | Selected probability | Raw confidence | Read latency |
|---|---|---:|---:|---:|---:|
| Jev Cloud (`jev-1.13.0`) | A: `verify_recipients` | 0.94 | 0.80 | 0.74 | 2365 ms |
| Laya CPU (`laya-rl-agent`) | A: `verify_recipients` | 0.9194 | 0.8971 | 0.6805 | 1631 ms |

The trial demonstrates the intended DLM + compact decision-read composition on local consumer
hardware. It does not yet pass the stricter claim that the local DLM can always emit a complete
project-native JSON object within two canvas blocks. The next runtime task is constrained/final-
channel decoding or a longer output budget, followed by the existing strict parser with no
field recovery.

Laya also warned that one checkpoint temperature was outside its accepted range and was clamped
to 0.5. Its confidence is therefore treated as uncalibrated and must not be compared numerically
with Jev confidence without backend-specific calibration.
