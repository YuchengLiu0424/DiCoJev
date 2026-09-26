# DiCoJev

**DiCoJev** is a local-first research system for **fast multimodal decision making** over **dynamically generated** action sets, with explicit **coverage-aware** feedback when the current choices are incomplete or insufficient.

Instead of assuming that a caller has already supplied the correct choices, the system lets a diffusion language model (DLM) construct candidate actions, then asks a pluggable decision backend two different questions:

1. **Is the candidate set adequate?**
2. **If it is adequate, which candidate should be selected?**

A controller uses those signals to choose one of four meta-actions:

```text
ACT | EXPAND | ABSTAIN | ESCALATE
```

The project is therefore not a fixed `DLM + Jev` or `DLM + Djev` pipeline. The stable system boundary is:

```text
Multimodal State
      |
      v
DLM Candidate Generator
      |
      v
Decision Harness
      |
      v
Pluggable DecisionBackend
      |
      v
Risk / Compute Controller
```

## Why this project exists

Fast classifiers and structured decision models are attractive because they return compact, probability-backed decisions instead of long autoregressive text. Their weakness is that they usually operate in a **closed world**: the set of labels or actions is assumed to be supplied correctly.

Open-world agents have a different failure mode. They may generate three plausible actions, assign 95% confidence to the best one, and still fail because the actually useful action was never generated.

DiCoJev makes that failure mode explicit. It separates:

```text
q_cov  = estimated adequacy of the generated candidate set
q_sel  = confidence/preference for the selected candidate within that set
```

These are not treated as the same probability.

## What the system does

For each decision round, the intended workflow is:

```text
observation + goal + tools + constraints
                  |
                  v
       multimodal DLM generation
                  |
                  v
        project-native DecisionSpec
                  |
                  v
 validate / repair / dedupe / assign IDs / add NOTA
                  |
                  v
          DecisionBackend read
           |              |
           v              v
        coverage       selection
           |              |
           +------+- -----+
                  v
             controller
      +-----------+-----------+-----------+
      |           |           |           |
     ACT        EXPAND      ABSTAIN     ESCALATE
```

`EXPAND` is important: low candidate-set coverage should be allowed to trigger more candidate generation instead of forcing a high-confidence choice among bad options.

## Default model and deployment philosophy

The default DLM family is `google/diffusiongemma-26B-A4B-it`, selected because it supports image-text input and diffusion-style generation and can be served locally. The architecture does not hard-code this model; generator and decision interfaces remain replaceable.

The preferred deployment is **local-first**. Hosted Jev is supported as a comparison backend, not as a required dependency.

## Decision backends

All decision systems implement the same project-owned backend contract. The repository is designed to support:

| Backend | Role |
|---|---|
| `MockDecisionBackend` | deterministic tests and offline development |
| `JevCloudBackend` | hosted structured-decision reference |
| `DjevLocalBackend` | local Jev-compatible DiffusionGemma structured-read reference |
| `CrossEncoderDecisionBackend` | conventional generate-then-rank baseline |
| `NativeDLMDecisionBackend` | project-owned diffusion structured-read path |

Using `DjevLocalBackend` after DLM generation intentionally creates **two diffusion inference stages**. That is a baseline. The native path is designed to let one DLM runtime eventually support both open candidate generation and structured probabilistic reads.

## How to read this repository

Different documents have different audiences. Do not treat every Markdown file as interchangeable.

- Start with this README if you want the project-level picture and the local workflow.
- Read [`docs/research/PROJECT_DESCRIPTION.md`](docs/research/PROJECT_DESCRIPTION.md) for the research problem, use cases, strengths, limitations, novelty, and paper-oriented framing.
- Read [`docs/design/ARCHITECTURE.md`](docs/design/ARCHITECTURE.md) for component ownership and runtime boundaries.
- Read [`docs/design/DECISION_SEMANTICS.md`](docs/design/DECISION_SEMANTICS.md) before changing coverage, confidence, NOTA, or controller semantics.
- Read [`docs/usage/LOCAL_SETUP.md`](docs/usage/LOCAL_SETUP.md) to run the supported local deployment shapes.
- Repository development and release sequencing live only under [`docs/governance/`](docs/governance/README.md).
- Coding agents should be pointed to [`agents/START_HERE.md`](agents/START_HERE.md), not asked to infer implementation policy from the README.

A complete human-facing documentation map is in [`docs/README.md`](docs/README.md).

## Local workflow

The project supports four deployment shapes behind the same application interface:

```text
A. offline development
   Fake/fixture generator -> MockDecisionBackend

B. local generation + conventional ranker
   local DiffusionGemma -> CrossEncoderDecisionBackend

C. local generation + local Djev reference
   local DiffusionGemma -> local Djev service

D. local generation + hosted Jev reference
   local DiffusionGemma -> JevCloudBackend

E. native target architecture
   one project-controlled DLM runtime -> generate() + structured_read()
```

Install the repository environment with:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Model servers are intentionally external to unit tests. Unit tests must run without a GPU, network connection, or API key.

For service-specific setup, environment variables, and expected request flow, follow [`docs/usage/LOCAL_SETUP.md`](docs/usage/LOCAL_SETUP.md). Configuration semantics are documented in [`docs/usage/CONFIGURATION.md`](docs/usage/CONFIGURATION.md).

## Project-native data flow

The DLM does **not** own the final Jev/Djev wire format. It produces a backend-neutral `DecisionSpec`. The deterministic harness then validates and compiles it.

This separation is intentional:

```text
DLM output
   -> DecisionSpec
   -> validation / normalization
   -> candidate IDs A/B/C/...
   -> synthetic NOTA
   -> backend-specific request
```

That means Jev, Djev, a cross-encoder, or a native diffusion read can be swapped without changing the generator's semantic output contract.

See [`docs/design/HARNESS.md`](docs/design/HARNESS.md) for the exact transformation pipeline.

## Jev-compatible coverage and selection

For Jev-compatible backends, coverage is represented as a normal `noul` question and selection as a normal `choice` question. The project does not invent a fourth Jev question field.

Conceptually:

```json
{
  "candidate_coverage": {
    "type": "noul",
    "instructions": "Does the candidate set contain at least one acceptable next action?"
  },
  "action": {
    "type": "choice",
    "instructions": "Choose the best acceptable next action.",
    "criteria": {
      "A": "...",
      "B": "...",
      "N": "None of the above"
    }
  }
}
```

The normalized result keeps candidate-set adequacy and conditional selection confidence as separate fields. Mathematical definitions and calibration rules live in [`docs/design/DECISION_SEMANTICS.md`](docs/design/DECISION_SEMANTICS.md).

## Repository layout

```text
DiCoJev/
├── README.md                       # public GitHub landing page
├── pyproject.toml
├── configs/                        # executable configuration profiles
├── docs/
│   ├── README.md                   # human documentation map
│   ├── research/                   # research story and paper starting point
│   ├── design/                     # normative system contracts
│   ├── usage/                      # local operation and configuration
│   ├── governance/                 # versioning and contribution policy
│   └── reference/                  # glossary and external references
├── agents/
│   ├── START_HERE.md               # coding-agent entry point
│   ├── EXECUTION_PROTOCOL.md       # machine-oriented working rules
│   └── tasks/                      # implementation tasks by release milestone
├── src/DiCoJev/
├── tests/
├── benchmarks/
├── examples/
├── scripts/
└── .github/
```

## Research documentation

The public README intentionally stops at project-level understanding and usage. For the complete research thesis—including application scenarios, limitations, comparison with Djev/Jev/generate-rank systems, explicit non-novel claims, proposed contributions, research hypotheses, and paper framing—read:

**[`docs/research/PROJECT_DESCRIPTION.md`](docs/research/PROJECT_DESCRIPTION.md)**
