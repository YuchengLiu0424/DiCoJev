# DiCoJev Documentation Map

This directory is the human-facing documentation tree. Each normative concept has one authoritative owner. Other documents should link to that owner instead of duplicating its definition.

| Topic | Authoritative file | Primary reader |
|---|---|---|
| GitHub overview and local entry workflow | [`../README.md`](../README.md) | users, visitors |
| Research problem, applications, strengths/weaknesses, contributions | [`research/PROJECT_DESCRIPTION.md`](research/PROJECT_DESCRIPTION.md) | researchers, paper authors |
| Prior work and novelty boundaries | [`research/RELATED_WORK.md`](research/RELATED_WORK.md) | researchers, reviewers |
| Evaluation hypotheses, metrics, ablations | [`research/EVALUATION.md`](research/EVALUATION.md) | experiment owners |
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
