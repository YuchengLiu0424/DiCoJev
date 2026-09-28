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

## Release decision

The deterministic v2 implementation and live Jev deletion check pass. The release remains
provisional: do not tag v2 until either Mercury completes a bounded initial-plus-expansion smoke run,
or the local DiffusionGemma endpoint completes an equivalent run, and one native-image local run is
persisted. The existing pull request may be reviewed, but these runtime gates should stay explicit.
