# Related Work and Novelty Boundaries

This file owns the project's comparison claims and explicit non-novelty boundaries.

## 1. Jev-style structured decision

Jev provides structured decision primitives over supplied state/questions/criteria. DiCoJev uses Jev as a reference backend and API style; it does not claim to invent compact structured decisions.

Reference: https://jevmodel.net/docs

## 2. Djev

Djev demonstrates Jev-style structured reads on DiffusionGemma and provides a useful local reference implementation. DiCoJev does not claim the structured diffusion read primitive itself as new.

Reference: https://github.com/mmastrac/djev

The project distinction is that DiCoJev owns the broader generated-action-set loop: candidate generation, candidate-set adequacy, controller policy, typed feedback, and regeneration.

## 3. Generate -> rank / verify / select

Generating candidates and then using a verifier/ranker is a mature pattern. DiCoJev must not claim novelty merely from placing a DLM generator before a selector.

## 4. NOTA / rejection

None-of-the-above and selective rejection mechanisms already exist. DiCoJev uses NOTA as one evidence source but distinguishes it from candidate-set coverage and controller actions.

## 5. Candidate-set coverage and conformal generation

Prior work studies set coverage/miscoverage and stopping/repeated generation. DiCoJev does not claim to invent candidate-set coverage. Its focus is the runtime integration of set-adequacy evidence with low-latency multimodal DLM generation, structured readout, and typed feedback-controlled refinement.

## 6. Generative action sets

Online decision-making work has studied expanding/generating action sets and the cost of obtaining new actions. DiCoJev should position its controller as an applied multimodal structured-decision system rather than claim the general generative-action-set idea is new.

## 7. Feedback and iterative refinement

Verifier feedback, retry loops, and iterative self-refinement are established ideas. The project does not claim that feedback loops themselves are new. The contribution being tested is the **small typed feedback interface** that connects candidate-set adequacy to regeneration while making feedback bandwidth and latency measurable.

## 8. Claims DiCoJev must not make

Do not claim that DiCoJev invented:

- generate -> verify -> select;
- dynamic action generation;
- NOTA/reject options;
- candidate-set coverage;
- conformal coverage;
- feedback loops or iterative refinement;
- diffusion structured read;
- Jev-style structured APIs.

## 9. Relationship to general agent frameworks

DiCoJev is not a workflow-orchestration competitor to LangGraph, Microsoft Agent Framework, Google
ADK, or similar platforms. Those projects emphasize stateful workflows, multi-agent coordination,
tools, sessions, deployment, and integrations. DiCoJev can be embedded as one decision node and is
specialized around generated candidate-set adequacy, bounded typed retries, and explicit
ACT/EXPAND/ABSTAIN/ESCALATE control.

Likewise, lightweight tool/code-agent libraries such as Hugging Face smolagents optimize the full
agent loop and model/tool interface. DiCoJev's narrower distinction is evaluating whether several
generated alternatives contain an acceptable choice before crossing an execution boundary.

References:

- https://docs.langchain.com/oss/python/langgraph/overview
- https://github.com/microsoft/agent-framework
- https://google.github.io/adk-docs/
- https://huggingface.co/docs/smolagents/index

## 10. Claims the project can test

The project can test whether the following combination is useful:

- multimodal diffusion-generated action sets;
- explicit `q_cov` distinct from `q_sel`;
- compact typed feedback instead of long-form retry reasoning;
- adaptive ACT/EXPAND/ABSTAIN/ESCALATE routing;
- a common harness across Jev, Djev, cross-encoder, and native DLM readers;
- a unified DLM runtime for generation and structured read;
- improved risk/latency/token trade-offs under controlled set failure.
