# Backend Module

This package contains implementations of the provider-neutral `DecisionBackend` interface.

The authoritative backend contract, capabilities, and provider-specific rules live in:

`docs/design/BACKENDS.md`

Keep provider wire schemas inside adapters and return normalized `DecisionBackendResult` objects to the rest of the application.
