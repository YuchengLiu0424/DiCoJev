# Contributing

This file is for human contributors. Coding-agent execution rules live under `agents/`.

## 1. Before editing

Read the documentation owner for the concept you plan to change. The ownership table is in `docs/README.md`.

Examples:

- changing `q_cov` semantics -> edit `docs/design/DECISION_SEMANTICS.md` first;
- adding backend capability -> edit `docs/design/BACKENDS.md`;
- changing branch/release scope -> edit `docs/governance/VERSION_CONTROL.md`;
- changing novelty claim -> edit `docs/research/RELATED_WORK.md`.

## 2. Development principles

- preserve backend-neutral public schemas;
- prefer typed interfaces and deterministic validation;
- keep GPU/network integration tests separate from unit tests;
- never commit credentials;
- never log image bytes by default;
- preserve raw and calibrated uncertainty separately;
- document any experimental preprocessing that changes model-visible information;
- do not claim a model score is calibrated without a fitted/evaluated calibration procedure.

## 3. Pull requests

A PR should state:

- what contract or behavior changed;
- which authoritative document owns that behavior;
- tests added/updated;
- hardware/network dependencies;
- research-metric implications where relevant.

Use the repository PR template.
