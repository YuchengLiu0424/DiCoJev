# Tests

The default suite is CPU-only and must not require GPU, network access, provider credentials,
or model downloads. Real Mercury/local-DLM/backend smoke tests use the `integration` marker and remain skipped
unless their documented `DICOJEV_RUN_LIVE_*` environment flag is explicitly enabled.
