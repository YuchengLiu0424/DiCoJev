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

`evaluate_v3.py` writes the matched Native/CrossEncoder/Djev acceptance comparison. Djev is run only
when `DICOJEV_DJEV_URL` is configured; otherwise the artifact retains an explicit hardware-waiver
status. When `JEV_API_KEY` is configured, the same candidates also reach hosted Jev as the real
independent reference for hosts where the local GPU deployment is unavailable.

`evaluate_v3_repeatability.py` performs at least two fixed-configuration sequential native reads,
persists every logit/decision/latency, and fails unless the maximum logit span is within the
declared tolerance and the selected ID is stable.

`evaluate_v4.py` recreates the deterministic v4 calibration and adaptive-compute report without a
model service. It fits calibration and independent coverage models on fixed train/validation/test
splits, then reports calibration, dependence, NOTA, feedback-policy, adaptive-compute, conformal,
and ablation tables. The optional CSV is suitable for plotting the risk-latency-token curve:

```powershell
.venv\Scripts\python.exe scripts\evaluate_v4.py `
  --output benchmarks/v4_evaluation.json `
  --curve-csv benchmarks/v4_risk_latency_token.csv `
  --plot benchmarks/v4_risk_latency_token.svg
```

This is controlled acceptance evidence. Its latency, token, and recovery values are fixture
accounting and must not be reported as live-model performance.

`evaluate_v4_live_jev.py` constructs adequate, acceptable-deleted, duplicate-added, and
distractor-added variants for each v1 task, keeps base tasks disjoint across train/validation/test,
and fits a live-score Platt calibrator. It submits those variants to hosted Jev and therefore must
only be run with authorization to send the fixture text to that external service.

`evaluate_v4_live_policies.py` runs typed, binary-retry, and long-form feedback through matched
Mercury-generation/hosted-Jev loops, then executes fixed-one, fixed-two, and learned adaptive
controllers. `evaluate_v4_verifier_correlation.py` compares local native LLaDA and hosted Jev on
the same balanced adequate/deleted sets. Both scripts invoke external services and persist full
normalized evidence without credentials.

`evaluate_v5.py` recreates the final offline acceptance report, including all controller actions,
text/multimodal cases, p50/p95 harness latency, feedback tokens, Python peak memory, retained live
risk-latency-token evidence, and shared-runtime cache equivalence.

`check_doc_ownership.py` validates that every Markdown target in the authoritative documentation
map exists. It is a release gate for documentation ownership consistency.
