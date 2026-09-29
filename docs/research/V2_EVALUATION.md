# v2 Closed-Loop Evaluation

## Controlled acceptance matrix

`benchmarks/v2_controlled.json` contains 11 deterministic conditions covering candidate deletion,
distractors, redundancy, unavailable tools, explicit constraints, NOTA, insufficient information,
expansion recovery, and multimodal ambiguity. `scripts/evaluate_v2.py` currently passes all 11 and
exercises ACT, EXPAND, ABSTAIN, and ESCALATE. These are harness acceptance fixtures; their scripted
coverage values are not empirical model-quality evidence.

## Live Jev candidate deletion

A matched live Jev check on 2026-09-28 reported the expected degradation:

| Condition | Coverage | Selection |
|---|---:|---|
| acceptable candidate retained | 0.95 | A |
| all acceptable candidates deleted | 0.39 | N |

`benchmarks/v2_jev_candidate_deletion.json` fixes the matched inputs, and
`benchmarks/v2_jev_deletion_live_result.json` retains the normalized result without credentials or
the raw provider envelope. `scripts/evaluate_v2_jev_deletion.py` can reproduce the report with
`JEV_API_KEY`.

## Live generator status

The local quantized DiffusionGemma text path was previously validated and remains slow but effective:
the retained trial generated 256 tokens in 175.5 seconds after loading a Q4 model that used roughly
29 GB resident memory. The HTTP endpoint is currently offline, and the earlier WSL CLI build could
not be located, so no live native-image generation was rerun. Native-image transport remains
request-shape-tested only.

Mercury credentials are now available through the supported `MERCURY_API_KEY` alias. Live testing
found and fixed the `/v1` URL composition, completion-token, overproduction, and round-budget issues.
One diagnostic run returned a valid eight-candidate initial set in 2.48 seconds and a second provider
response in 2.25 seconds, but that run predated the round-budget fix and therefore produced no usable
expansion. After reserving four of eight candidate slots for expansion, the provider timed out once
during expansion at 60 seconds and once during initial generation at 120 seconds. This is evidence
that the adapter can reach and parse Mercury, but it is not a passing closed-loop smoke test.

## Runtime closure and release decision

The remaining runtime checks were completed on 2026-09-29. Mercury completed a bounded
initial-plus-expansion loop. The pinned DiffusionGemma `llama.cpp` runner completed a real CPU
generation in about 251 seconds. The local LLaDA-V checkpoint loaded all six shards through an
isolated Transformers 4.40 environment, returned valid candidate JSON through the project-owned
OpenAI-compatible server, and correctly identified a native red PNG as `red`. The image request
took about 447 seconds on CPU, so it is a correctness path rather than an interactive deployment.

The cross-runtime record is stored in `benchmarks/v2_runtime_matrix.json`. Djev remains an explicit
hardware-limited reference rather than a failed local pipeline. These results close the stated v2
runtime gates and support an `v2.0.0-rc1` release candidate.
