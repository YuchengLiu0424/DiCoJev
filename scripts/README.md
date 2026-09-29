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
