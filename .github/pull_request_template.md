## Summary

Describe the behavior changed and the active milestone.

## Source of truth

- [ ] I identified the authoritative document for this change using `docs/README.md`.
- [ ] I did not duplicate normative definitions into another document.

## Scope

- [ ] The change is inside the active milestone defined by `docs/governance/VERSION_CONTROL.md`.
- [ ] No later-milestone feature was pulled forward without an invariant/bug-fix reason.

## Verification

- [ ] Offline unit tests pass.
- [ ] Relevant integration tests pass, or hardware/network-dependent skips are listed below.
- [ ] No API keys, model weights, raw private data, or image bytes were committed.
- [ ] Raw and calibrated scores remain distinct.
- [ ] Backend/provider details remain behind adapters.
- [ ] Typed feedback remains bounded and separate from provider wire schemas.
- [ ] Feedback/compiler/controller responsibilities remain separated.

## Integration tests / limitations

<!-- List hardware, model-server, or provider requirements and any unrun checks. -->
