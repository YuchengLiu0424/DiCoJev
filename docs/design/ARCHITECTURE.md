# System Architecture

This file is the authoritative definition of component ownership, interfaces, and runtime data flow. It does not define research novelty or release milestones.

## 1. Stable architecture

```text
DecisionRequest
      |
      v
StateNormalizer
      |
      v
CandidateGenerator (DLM) <-------------------------------+
      |                                                   |
      v                                                   |
DecisionSpec                                              |
      |                                                   |
      v                                                   |
DecisionHarness                                           |
  parse / repair / validate                               |
  normalize / dedupe / constraint checks                  |
  stable candidate IDs / synthetic NOTA                   |
      |                                                   |
      v                                                   |
DecisionBackend                                           |
  coverage + selection + quality diagnostics              |
      |                                                   |
      v                                                   |
RiskController                                            |
  meta-action + typed FeedbackBundle                      |
      |                                                   |
      +--> ACT --> Environment/Tool                        |
      +--> ABSTAIN                                         |
      +--> ESCALATE --> EscalationTarget                  |
      |                                                   |
      +--> EXPAND --> FeedbackCompiler --> LoopContext ---+
```

## 2. Project boundary

```text
DLM CandidateGenerator
+ deterministic DecisionHarness
+ pluggable DecisionBackend
+ RiskController
+ typed FeedbackCompiler / LoopContext
```

Jev, Djev, or model-provider wire fields must not become required public project fields unless promoted through an explicit design change.

## 3. Public request

`DecisionRequest` conceptually contains:

```text
state:
  text observation
  images
  structured environment state

goal
available tools/actions
constraints
bounded history
risk/compute budget
```

Images remain first-class references. Unsupported image capability must be explicit rather than silently converted into a caption and labeled native multimodal.

`ImageRef` accepts exactly one of a local path, provider-accessible reference/data URL, or in-memory
bytes. The v2 reference transport accepts PNG, JPEG, GIF, and WebP up to 10 MiB per image. Local
paths and bytes are converted to data URLs only at the provider boundary; raw bytes are excluded
from response traces and default logs.

## 4. CandidateGenerator

The generator owns open semantic action construction, not final provider JSON.

```python
class CandidateGenerator(Protocol):
    async def generate(
        self,
        request: DecisionRequest,
        context: LoopContext | None = None,
    ) -> DecisionSpec: ...
```

The supported implementation family is diffusion language models: hosted Mercury for fast text
generation and local DiffusionGemma for local/private or native-image generation.

## 5. DecisionSpec

`DecisionSpec` is the backend-neutral representation between open generation and deterministic compilation. Exact uncertainty semantics are owned by `DECISION_SEMANTICS.md`.

## 6. DecisionHarness

The harness transforms probabilistic model output into a safe, comparable decision problem. It owns parsing/repair, validation, candidate canonicalization, deduplication, tool/constraint checks, stable IDs, NOTA injection, backend compiler selection, normalized backend-result handling, and trace assembly.

Detailed rules are in `HARNESS.md`.

## 7. DecisionBackend

A backend evaluates an already constructed candidate set; it does not mutate semantic candidates.

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

Normalized results include coverage evidence, selection evidence, candidate-quality diagnostics, NOTA evidence when available, and latency/diagnostics.

## 8. RiskController

The controller converts normalized evidence and budget state into:

```text
MetaAction
FeedbackBundle
reason code
```

It must not call provider APIs directly and must not generate free-form reasoning text as its canonical interface.

## 9. FeedbackCompiler

The compiler maps typed feedback plus prior candidate state into `LoopContext` / generator-facing regeneration constraints. It does not decide whether to expand; it only compiles an already chosen feedback/action policy.

The canonical protocol is defined in `FEEDBACK_PROTOCOL.md`.

## 10. EscalationTarget

An escalation target is separate from a decision backend. It can represent a slower planner, larger model, human approval path, or domain-specific fallback.
Its normalized result records the target, accepted/unavailable status, and a bounded message.

## 11. Djev topology

With DiffusionGemma generation followed by Djev:

```text
DiffusionGemma generation service
      |
      v
candidate set
      |
      v
Djev structured-read service
      |
      v
coverage + selection
```

This is two diffusion inference stages and may involve two model-service instances. Benchmarks must report them separately.

## 12. Native DLM topology

The target native path preserves the public interfaces while moving structured read under project control:

```text
Project DLM Runtime
  |
  +--> generate(request, loop_context) -> DecisionSpec
  |
  +--> structured_read(state, candidates) -> DecisionBackendResult
```

Weight/process sharing, multimodal preprocessing reuse, or cached state are optimizations only when correctness is preserved and measured.

## 13. Capability negotiation

Backends declare capabilities such as:

```text
supports_text
supports_images
supports_native_multimodal
supports_binary_coverage
supports_choice_distribution
supports_calibrated_output
requires_single_token_labels
requires_network
requires_api_key
```

Capability mismatch must fail explicitly.

## 14. Error and telemetry policy

Typed failures include generator timeout, invalid `DecisionSpec`, empty candidate set, backend unavailable, capability mismatch, malformed probabilities, feedback compilation failure, budget exhaustion, and unavailable escalation.

Default behavior is fail-closed: infrastructure/evidence failure does not become `ACT`.

Telemetry records component latency, candidate evolution, backend identity, raw/calibrated evidence, feedback codes and payload size, controller reason codes, and execution outcomes when available. Raw images and secrets are never logged by default.
