# Documentation Map

This directory is the human-facing documentation tree. Its purpose is to prevent one concept from being defined in multiple files.

## Document ownership contract

Every important concept has exactly one authoritative owner. Other files may link to that owner, but should not restate the full definition.

| Topic | Authoritative file | Primary reader |
|---|---|---|
| GitHub-level overview and entry workflow | [`../README.md`](../README.md) | users, visitors, evaluators |
| Research problem, applications, strengths/weaknesses, contributions | [`research/PROJECT_DESCRIPTION.md`](research/PROJECT_DESCRIPTION.md) | researchers, authors, reviewers |
| Prior work and novelty boundaries | [`research/RELATED_WORK.md`](research/RELATED_WORK.md) | researchers, paper authors |
| Research hypotheses, benchmarks, metrics, ablations | [`research/EVALUATION.md`](research/EVALUATION.md) | researchers, experiment owners |
| Component boundaries and data flow | [`design/ARCHITECTURE.md`](design/ARCHITECTURE.md) | engineers, architects |
| Coverage/confidence/NOTA/controller meaning | [`design/DECISION_SEMANTICS.md`](design/DECISION_SEMANTICS.md) | model + evaluation engineers |
| `DecisionBackend` contract and backend-specific behavior | [`design/BACKENDS.md`](design/BACKENDS.md) | backend engineers |
| DLM output, parsing, validation, candidate compilation | [`design/HARNESS.md`](design/HARNESS.md) | harness engineers |
| Local deployment and service startup | [`usage/LOCAL_SETUP.md`](usage/LOCAL_SETUP.md) | developers, users |
| Configuration keys/profiles | [`usage/CONFIGURATION.md`](usage/CONFIGURATION.md) | developers, operators |
| Version scope, branches, tags, acceptance gates | [`governance/VERSION_CONTROL.md`](governance/VERSION_CONTROL.md) | maintainers, release owners |
| Human contribution process | [`governance/CONTRIBUTING.md`](governance/CONTRIBUTING.md) | contributors |
| Release history | [`governance/CHANGELOG.md`](governance/CHANGELOG.md) | users, maintainers |
| Terms and external sources | [`reference/`](reference/) | all readers |

## Files that are deliberately not authoritative

The `agents/` tree is an execution layer for coding agents. It never redefines research semantics, architecture, or release scope. Agent files point to the human-owned source of truth and translate it into ordered implementation work.

Configuration files under `configs/` are executable defaults. They do not define the meaning of coverage, selection, or release scope; they only instantiate documented settings.

Examples under `examples/` demonstrate shapes. They do not supersede the schema/design documents.

## Editing rule

When a concept changes:

1. edit its authoritative document first;
2. update code/tests/configs that implement it;
3. update links or short summaries elsewhere only if they became inaccurate;
4. never copy a large normative section into another document for convenience.
