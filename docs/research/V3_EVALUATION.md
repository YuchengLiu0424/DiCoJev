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
  semantic candidates to Native, CrossEncoder, and hosted Jev backends. All select `A`; coverage is
  0.880797, 0.88, and 0.97 respectively. Hosted Jev 1.13.0 is the real independent reference for
  the abandoned local Djev deployment.

## Runtime reproducibility

The formal fixed-configuration text repetition series in
`benchmarks/v4_native_repeatability.json` contains five sequential runs through the same local
LLaDA checkpoint, state, prompt construction, candidates, and read mode. Coverage and selection
logit spans were exactly `0.0`, and all five runs selected `A`, passing the predeclared `0.02`
absolute-logit tolerance.

Two separate sequential native-image runs—before and after enabling the vision-feature cache—gave
identical coverage logits `[8.8671875, 9.640625]` and selection logits
`[13.1328125, 8.171875]`. The acceptance tolerance is absolute logit difference at most `0.02` and
unchanged selected ID. The opt-in batched run remained within tolerance: coverage was identical,
the first selection logit differed by `0.015625`, and selection remained `A`.

## Djev replacement and hardware waiver

The comparison runner includes the Djev adapter and will execute it when `DICOJEV_DJEV_URL` is
configured. It is recorded as `not_run` on this host because the patched vLLM DiffusionGemma stack
exceeds available consumer GPU memory. The roadmap therefore permits hosted Jev as the independent
matched reference when this explicit condition holds. Djev wire compatibility and normalization
remain covered by offline tests; the report does not claim that hosted Jev is a local Djev run.

## Decision

The v3 interface, correctness, controller-neutrality, and available runtime gates pass. CPU-native
multimodal inference remains noninteractive, and batching is not enabled by default because its
matched CPU result regressed relative to cached sequential reads. Those performance limits are
documented rather than treated as evidence against coverage-aware control.
