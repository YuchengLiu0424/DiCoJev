# v3 Evaluation and Release Decision

## Acceptance summary

- The project-owned `NativeDLMDecisionBackend` returns normalized coverage and selection evidence
  without a Djev server.
- Deterministic read canvases, unique single-token labels, finite logits, and output dimensions are
  validated before evidence reaches the controller.
- Backend selection remains configuration-only and does not alter the public decision API.
- A native-backend orchestrator test exercises `EXPAND`, typed `MISSING_ACTION` feedback, candidate
  regeneration, reevaluation, and final `ACT` without backend-specific controller behavior.
- The controlled matched comparison in `benchmarks/v3_matched_backends.json` supplies the same two
  semantic candidates to Native and CrossEncoder backends. Both select `A` with probability
  0.952574; their independent coverage values are 0.880797 and 0.88.

## Runtime reproducibility

Two separate sequential native-image runs—before and after enabling the vision-feature cache—gave
identical coverage logits `[8.8671875, 9.640625]` and selection logits
`[13.1328125, 8.171875]`. The acceptance tolerance is absolute logit difference at most `0.02` and
unchanged selected ID. The opt-in batched run remained within tolerance: coverage was identical,
the first selection logit differed by `0.015625`, and selection remained `A`.

## Djev hardware waiver

The comparison runner includes the Djev adapter and will execute it when `DICOJEV_DJEV_URL` is
configured. It is recorded as `not_run` on this host because the patched vLLM DiffusionGemma stack
exceeds available consumer GPU memory. Djev wire compatibility and normalization remain covered by
offline tests. This is an explicit hardware waiver, not substituted model evidence.

## Decision

The v3 interface, correctness, controller-neutrality, and available runtime gates pass. CPU-native
multimodal inference remains noninteractive, and batching is not enabled by default because its
matched CPU result regressed relative to cached sequential reads. Those performance limits are
documented rather than treated as evidence against coverage-aware control.
