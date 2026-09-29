# v3 Implementation Status

## Implemented foundation

- `LladaGenerator` is a first-class local multimodal generator adapter rather than an alias for the
  DiffusionGemma deployment.
- OpenAI-compatible generators share a bounded structured-output repair policy. One retry is the
  default; the invalid response and validation reason are supplied to the repair round, and usage
  and latency include all attempts.
- `NativeDLMDecisionBackend` implements the existing backend protocol with separate binary coverage
  and categorical selection reads.
- Native read canvases are deterministic, compact, and backend-owned. Candidate labels are checked
  for uniqueness and single-token safety before any model read.
- Logits are checked for count and finiteness, normalized independently for coverage and selection,
  and retained in diagnostics.
- The native runtime is injected and can execute in the same process as model weights. Core imports
  remain CPU-only and do not require a particular inference framework.

## Runtime integration boundary

The backend accepts an object implementing `read(NativeReadRequest)`. A concrete LLaDA or
DiffusionGemma runtime must score the request's exact label set on the supplied prompt and native
multimodal state. This deliberate boundary prevents generated text or a chat-completion probability
from being misreported as a structured read.

The current LLaDA HTTP server exposes generation, not label logits. Connecting it to the native
backend therefore requires a same-process scoring implementation or a new explicit logit endpoint;
that hardware-dependent integration is the next v3 runtime task.
