# DiCoJev Documentation Map

This directory is the human-facing documentation tree. Each normative concept has one authoritative owner. Other documents should link to that owner instead of duplicating its definition.

| Topic | Authoritative file | Primary reader |
|---|---|---|
| GitHub overview and local entry workflow | [`../README.md`](../README.md) | users, visitors |
| Research problem, applications, strengths/weaknesses, contributions | [`research/PROJECT_DESCRIPTION.md`](research/PROJECT_DESCRIPTION.md) | researchers, paper authors |
| Prior work and novelty boundaries | [`research/RELATED_WORK.md`](research/RELATED_WORK.md) | researchers, reviewers |
| Evaluation hypotheses, metrics, ablations | [`research/EVALUATION.md`](research/EVALUATION.md) | experiment owners |
| v1 local runtime and backend evaluation evidence | [`research/LOCAL_DLM_TRIAL.md`](research/LOCAL_DLM_TRIAL.md), [`research/V1_EVALUATION.md`](research/V1_EVALUATION.md) | researchers, reviewers |
| v2 closed-loop and live deletion evidence | [`research/V2_EVALUATION.md`](research/V2_EVALUATION.md) | researchers, reviewers |
| v3 native-read evidence | [`research/V3_EVALUATION.md`](research/V3_EVALUATION.md), [`research/V3_IMPLEMENTATION.md`](research/V3_IMPLEMENTATION.md) | researchers, runtime engineers |
| v4 calibration and adaptive-policy evidence | [`research/V4_EVALUATION.md`](research/V4_EVALUATION.md) | researchers, reviewers |
| v5 unified runtime and 1.0 release evidence | [`research/V5_EVALUATION.md`](research/V5_EVALUATION.md) | users, researchers, maintainers |
| Final holistic project review and evidence boundaries | [`research/FINAL_PROJECT_REVIEW.md`](research/FINAL_PROJECT_REVIEW.md) | users, reviewers, maintainers |
| Component boundaries and runtime flow | [`design/ARCHITECTURE.md`](design/ARCHITECTURE.md) | engineers |
| Coverage, selection, NOTA, controller semantics | [`design/DECISION_SEMANTICS.md`](design/DECISION_SEMANTICS.md) | engineers, researchers |
| Typed low-bandwidth feedback protocol | [`design/FEEDBACK_PROTOCOL.md`](design/FEEDBACK_PROTOCOL.md) | engineers, researchers |
| Backend contract and provider adapters | [`design/BACKENDS.md`](design/BACKENDS.md) | backend implementers |
| Generator-to-decision harness behavior | [`design/HARNESS.md`](design/HARNESS.md) | harness implementers |
| Local setup and deployment shapes | [`usage/LOCAL_SETUP.md`](usage/LOCAL_SETUP.md) | operators |
| Real DLM serving/runtime plan | [`usage/MODEL_RUNTIME.md`](usage/MODEL_RUNTIME.md) | GPU/runtime engineers |
| Configuration key meanings | [`usage/CONFIGURATION.md`](usage/CONFIGURATION.md) | operators, developers |
| Milestone scope / branch / release gates | [`governance/VERSION_CONTROL.md`](governance/VERSION_CONTROL.md) | maintainers, agents |
| Contribution process | [`governance/CONTRIBUTING.md`](governance/CONTRIBUTING.md) | contributors |
| Terms | [`reference/GLOSSARY.md`](reference/GLOSSARY.md) | everyone |
| External references | [`reference/REFERENCES.md`](reference/REFERENCES.md) | researchers |

Coding-agent-only execution material lives under [`../agents/`](../agents/). Agent files may translate human-owned contracts into implementation steps, but they do not redefine research semantics, design contracts, or release scope.
