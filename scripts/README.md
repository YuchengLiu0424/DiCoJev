# Operational Scripts

This directory contains local service startup, smoke-test, benchmark, calibration, and reproduction helpers as they are implemented.

Operator-facing setup belongs in `docs/usage/LOCAL_SETUP.md`; release scope belongs in `docs/governance/VERSION_CONTROL.md`.

Scripts must not embed credentials, private dataset paths, or model weights.

`evaluate_v2.py` runs the offline v2 corruption/recovery matrix and can persist its complete
per-round report with `--output results/v2_controlled.json`.

`evaluate_v2_jev_deletion.py` runs the fixed matched candidate-deletion pair through hosted Jev and
requires an explicit output path so the normalized live evidence is retained.
