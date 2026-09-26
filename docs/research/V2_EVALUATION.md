# v2 Closed-Loop Evaluation

## Controlled acceptance matrix

`benchmarks/v2_controlled.json` contains 11 deterministic conditions covering candidate deletion,
distractors, redundancy, unavailable tools, explicit constraints, NOTA, insufficient information,
expansion recovery, and multimodal ambiguity. `scripts/evaluate_v2.py` currently passes all 11 and
exercises ACT, EXPAND, ABSTAIN, and ESCALATE. These are harness acceptance fixtures; their scripted
coverage values are not empirical model-quality evidence.

## Live Jev candidate deletion

A matched live Jev check reported the expected degradation:

| Condition | Coverage | Selection |
|---|---:|---|
| acceptable candidate retained | 0.98 | A |
| all acceptable candidates deleted | 0.15 | N |

The original raw provider envelope was not retained, so this table is supporting evidence rather
than a complete reproducibility artifact. `benchmarks/v2_jev_candidate_deletion.json` now fixes the
matched inputs, and `scripts/evaluate_v2_jev_deletion.py` persists normalized live results when run
with `JEV_API_KEY`. Future release evidence should use that saved output rather than manually copied
scores.

## Live generator status

The local quantized DiffusionGemma text path was previously validated and is slow but effective.
At this checkpoint no `INCEPTION_API_KEY` was configured, the local DLM endpoint was offline, and no
live native-image generation was rerun. Mercury is therefore adapter-tested only; local native-image
transport is request-shape-tested only. These limitations must remain visible until the corresponding
live report is persisted.
