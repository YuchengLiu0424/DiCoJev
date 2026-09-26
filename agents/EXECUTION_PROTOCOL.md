# Coding Agent Execution Protocol

This file describes how a coding agent should work. It does not define what the system means or what each release contains.

## 1. Start-of-task procedure

1. Determine the active milestone from the user/task context and `docs/governance/VERSION_CONTROL.md`.
2. Read the corresponding `agents/tasks/vN.md`.
3. Inspect the existing code/tests before editing.
4. Map each requested code change to an authoritative design document.
5. Refuse scope creep internally: later-milestone work is not implemented on the current branch unless required by an invariant/bug fix.

## 2. Implementation order

Within a milestone, prefer:

```text
schemas/interfaces
-> deterministic implementation
-> unit tests
-> external-service adapter
-> integration tests
-> example/config
-> docs consistency check
```

Do not start GPU/model-server integration until the deterministic contracts it depends on have tests.

## 3. External services

- never require Jev, Djev, Hugging Face, or a GPU for unit tests;
- use recorded fixtures/mocks for provider responses;
- mark network/GPU tests explicitly;
- read API keys from environment variables only;
- keep service base URLs configurable;
- propagate timeout/cancellation explicitly.

## 4. Testing protocol

For each implementation slice:

1. add/update focused unit tests;
2. run the smallest relevant test target;
3. run full offline `pytest` before declaring the milestone complete;
4. run integration/hardware suites only when their prerequisites are available;
5. report skipped integration coverage clearly rather than pretending it passed.

## 5. Documentation protocol

Do not duplicate normative text into agent files.

When behavior changes, update the owning human document:

- decision semantics -> `docs/design/DECISION_SEMANTICS.md`;
- component/interface -> `docs/design/ARCHITECTURE.md`;
- backend behavior -> `docs/design/BACKENDS.md`;
- harness behavior -> `docs/design/HARNESS.md`;
- operator setup -> `docs/usage/*`;
- release scope -> `docs/governance/VERSION_CONTROL.md`.

Then keep agent task files limited to implementation instructions.

## 6. Completion report

At the end of a milestone implementation, report:

```text
implemented files/components
unit tests and result
integration tests and result/skips
known hardware/provider limitations
acceptance-gate items satisfied
acceptance-gate items not satisfied
contract changes, if any
```

Do not create a release tag unless explicitly asked and all required acceptance-gate items are satisfied.
