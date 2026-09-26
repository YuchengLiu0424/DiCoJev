# System Architecture

This file is the authoritative definition of component ownership, interfaces, and runtime data flow. It does not define research novelty, release milestones, or coding-agent work order.

## 1. Stable architecture

```text
DecisionRequest
      |
      v
StateNormalizer
      |
      v
CandidateGenerator (DLM)
      |
      v
DecisionSpec
      |
      v
DecisionHarness
  - parse / repair
  - validate
  - normalize / dedupe
  - tool/constraint checks
  - assign stable candidate IDs
  - inject synthetic NOTA
      |
      v
DecisionBackend
  - JevCloud
  - DjevLocal
  - CrossEncoder
  - NativeDLMRead
      |
      v
DecisionBackendResult
  - coverage evidence
  - selection evidence
  - candidate-quality diagnostics
      |
      v
RiskController
      |
      +--> ACT ----------> Environment/Tool
      +--> EXPAND -------> CandidateGenerator
      +--> ABSTAIN
      +--> ESCALATE -----> EscalationTarget
```

## 2. Architectural invariant

The project boundary is:

```text
DLM Candidate Generator
+ deterministic Decision Harness
+ pluggable DecisionBackend
+ RiskController
```

No Jev-, Djev-, or model-provider-specific field is allowed to become a required public project schema field unless it is promoted through an explicit design change.

## 3. Public request

A `DecisionRequest` conceptually contains:

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

Images remain first-class references. Whether a backend can consume them is represented as a backend capability, not silently converted to captions.

## 4. CandidateGenerator

The generator is responsible for **open semantic action construction**, not final provider wire format.

Minimum interface:

```python
class CandidateGenerator(Protocol):
    async def generate(
        self,
        request: DecisionRequest,
        context: ExpansionContext | None = None,
    ) -> DecisionSpec: ...
```

`ExpansionContext` contains prior candidates, reason for expansion, and remaining compute/candidate budget.

Default implementation family: DiffusionGemma.

## 5. DecisionSpec

`DecisionSpec` is the stable internal representation between open generation and deterministic compilation. It contains candidate semantics and task instructions but no Jev-specific answer envelope.

The exact schema and uncertainty semantics are owned by [`DECISION_SEMANTICS.md`](DECISION_SEMANTICS.md).

## 6. DecisionHarness

The harness is deterministic wherever possible. It is responsible for making generated content safe and comparable enough to pass to a decision backend.

It owns:

- bounded JSON extraction/repair;
- schema validation;
- canonicalization;
- semantic/string deduplication policy;
- tool existence checks;
- obvious constraint checks;
- candidate ID allocation;
- NOTA insertion;
- backend compiler selection;
- normalized backend response handling;
- per-round trace assembly.

Detailed behavior is owned by [`HARNESS.md`](HARNESS.md).

## 7. DecisionBackend

The backend answers questions **about an already constructed candidate set**. It does not mutate semantic candidates.

Minimum normalized contract:

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

The normalized result includes coverage evidence, selection distribution/confidence, diagnostics, and latency. Backend-specific wire schemas remain private to each adapter.

Details: [`BACKENDS.md`](BACKENDS.md).

## 8. RiskController

The controller consumes normalized evidence and budget state. It must not call provider APIs directly.

Conceptually:

```python
controller.decide(
    coverage,
    selection,
    candidate_quality,
    budget,
    round_state,
) -> ControllerDecision
```

Allowed meta-actions:

```text
ACT
EXPAND
ABSTAIN
ESCALATE
```

The exact meaning of these actions is defined in [`DECISION_SEMANTICS.md`](DECISION_SEMANTICS.md).

## 9. EscalationTarget

An escalation target is deliberately separate from `DecisionBackend`. It represents a slower or higher-authority path, such as:

- slow planner;
- larger model;
- human approval;
- domain-specific fallback.

A backend scores the current decision problem; an escalation target takes ownership of a broader next-step decision. Conflating them would make fast/slow routing impossible to measure cleanly.

## 10. Djev execution topology

When DiffusionGemma is the candidate generator and DjevLocal is the backend:

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

This is two diffusion inference stages and potentially two service/runtime instances. Metrics must report them separately.

## 11. Native DLM execution topology

The target native path preserves the same external interfaces but moves the decision read under project control:

```text
Project DLM Runtime
  |
  +--> generate(request) -> DecisionSpec
  |
  +--> structured_read(state, candidates) -> DecisionBackendResult
```

The first implementation may still use separate passes. Runtime weight sharing, common multimodal preprocessing, cached state, or other reuse is an optimization only when it preserves correctness and can be measured explicitly.

## 12. Capability negotiation

Every backend advertises capabilities such as:

```text
supports_text
supports_images
supports_choice_distribution
supports_binary_coverage
supports_calibrated_output
supports_native_multimodal
requires_single_token_labels
requires_network
requires_api_key
```

The harness fails explicitly when a requested evaluation path exceeds backend capability. It must not silently downgrade native multimodal input to captions.

## 13. Error policy

Core failures are typed:

- generator timeout;
- invalid `DecisionSpec` after bounded repair;
- empty candidate set;
- backend unavailable;
- backend capability mismatch;
- invalid probability normalization;
- budget exhausted;
- escalation unavailable.

The default policy for uncertain infrastructure failures is fail-closed: do not convert them into an `ACT` decision.

## 14. Telemetry boundary

Telemetry records:

- component latency;
- candidate evolution across rounds;
- backend identity;
- raw versus calibrated scores;
- controller reason codes;
- execution outcome when available.

Raw images are not logged by default. Credentials are never logged. Any raw model text logging must be explicit and configurable.
