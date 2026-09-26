# Decision Backend Contract

This file owns the behavior and compatibility requirements for decision backends.

## 1. Purpose

A `DecisionBackend` evaluates an already constructed candidate set. It does not generate or rewrite semantic actions. It also does not emit canonical DiCoJev feedback codes; it returns normalized evidence consumed by the controller/feedback layer.

Normalized conceptual interface:

```python
class DecisionBackend(Protocol):
    capabilities: BackendCapabilities

    async def decide(
        self,
        state: MultimodalState,
        spec: DecisionSpec,
        candidates: list[Candidate],
    ) -> DecisionBackendResult: ...
```

## 2. Required normalized outputs

A backend should expose, when supported:

- candidate-set coverage evidence;
- selected candidate ID;
- selection probability/score distribution;
- selection confidence;
- NOTA evidence if used;
- backend/model identity;
- raw diagnostics;
- latency;
- calibration metadata.

If a backend cannot natively estimate coverage, it must declare that limitation and use an explicitly named baseline method. It may not silently substitute top-1 selection confidence for `q_cov`.

## 3. Capability declaration

Suggested fields:

```text
supports_text
supports_images
supports_native_multimodal
supports_binary_coverage
supports_choice_distribution
supports_score
requires_single_token_labels
requires_network
requires_api_key
supports_calibrated_output
```

## 4. MockDecisionBackend

Purpose:

- deterministic unit tests;
- offline controller testing;
- reproducible fixtures;
- CI without GPU/network.

It must be able to return scripted coverage and selection distributions and typed failures.

## 5. JevCloudBackend

Purpose: hosted structured-decision reference.

Rules:

- API key only from environment/secret configuration;
- provider wire shape remains inside the adapter/compiler;
- coverage uses a dedicated `noul` question;
- selection uses `choice`;
- no requirement that Jev receive original images if its supported state contract does not accept them; capability mismatch must be explicit;
- network latency must be reported separately from local harness latency.

Jev documentation: https://jevmodel.net/docs

## 6. DjevLocalBackend

Purpose: local diffusion structured-read reference.

Rules:

- connect through a configurable local endpoint rather than vendoring/forking Djev in the first integration;
- compile Jev-compatible `noul` and `choice` questions;
- validate candidate labels against tokenization requirements;
- preserve Djev diagnostics when available;
- support image transport only when the connected Djev service advertises it;
- report decision-read latency separately from generator latency.

When paired with a DiffusionGemma generator, this backend creates a two-diffusion-stage architecture and must be labeled as such in benchmarks.

Djev reference: https://github.com/mmastrac/djev

## 7. CrossEncoderDecisionBackend

Purpose: mature generate-then-rank baseline.

Selection can score `(state, goal, candidate)` pairs and normalize candidate scores.

Coverage must be a separately named method, for example:

- explicit binary set-adequacy classifier;
- NOTA/reject head;
- heuristic baseline;
- learned set encoder.

Do not define:

```text
q_cov := max candidate score
```

without labeling it as an intentionally weak proxy baseline.

## 8. NativeDLMDecisionBackend

Purpose: project-owned DLM structured-read path.

It should support:

- deterministic decision templates/canvases;
- compact candidate labels;
- binary coverage read;
- categorical selection read;
- exact or well-defined probability extraction;
- stable numerical normalization;
- diagnostics for diffusion steps/samples/read mode;
- same-process use of the DLM runtime where supported.

The backend may borrow technical ideas demonstrated by Djev, but it should not require a Djev server at the project boundary.

## 9. Independent coverage backend / verifier

The architecture permits a coverage estimator that differs from the selection backend. This is important for studying correlated failures when one DLM both generates and judges its own candidates.

If split verification is enabled, normalized output should record:

```text
coverage_backend
selection_backend
```

separately.

## 10. Backend comparison rule

Every backend benchmark should receive the same normalized semantic state and candidate set as far as its declared modality capabilities allow. Any preprocessing that changes available information—such as image captioning—must be logged as a distinct experimental condition.
