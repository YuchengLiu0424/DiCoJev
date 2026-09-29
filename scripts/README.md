# Operational Scripts

This directory contains local service startup, smoke-test, benchmark, calibration, and reproduction helpers as they are implemented.

Operator-facing setup belongs in `docs/usage/LOCAL_SETUP.md`; release scope belongs in `docs/governance/VERSION_CONTROL.md`.

Scripts must not embed credentials, private dataset paths, or model weights.

`evaluate_v2.py` runs the offline v2 corruption/recovery matrix and can persist its complete
per-round report with `--output results/v2_controlled.json`.

`evaluate_v2_jev_deletion.py` runs the fixed matched candidate-deletion pair through hosted Jev and
requires an explicit output path so the normalized live evidence is retained.

`llada_openai_server.py` serves the separately downloaded LLaDA-V checkpoint on port 8002 using
its dedicated Python environment. It initializes the SigLIP architecture locally and loads the
vision weights embedded in the six checkpoint shards, so inference does not require a second
model download. `runtime_matrix.py` reports configured credentials, local weight presence, and
live endpoint availability without printing secret values.

On Windows, `start_llada.ps1` validates the expected model, source, and Python paths before starting
the server in the foreground. Override its parameters when the runtime is installed elsewhere.

After starting it, exercise the first-class adapter with:

```powershell
.venv\Scripts\python.exe scripts\runtime_smoke.py --generator llada --timeout 600
```

All OpenAI-compatible candidate adapters share one bounded structured-output repair attempt by
default. The retry includes the rejected response and validation reason; usage and latency include
both attempts. Configuration can select LLaDA with `generator_kind: llada`.

`native_read_smoke.py` sends the same state and candidate set through the LLaDA server's explicit
masked-label `/v1/structured-read` endpoint. It performs separate binary coverage and categorical
selection reads and can persist normalized evidence with `--output`.

The server keeps up to two projected vision-feature entries in a content-addressed LRU cache by
default. Set `LLADA_VISION_CACHE_ENTRIES=0` to disable it or another nonnegative integer to change
the bound. Structured-read diagnostics report `vision_cache_hit`; prompt-specific language-model
forwards are never cached.

The server also exposes `/v1/structured-read-batch`. Enable it through `batch_reads: true` in the
native backend configuration or `native_read_smoke.py --batch-reads`. It is deliberately disabled
by default because the matched CPU trial was slower than cached sequential reads; it should be
reevaluated on an accelerator.
