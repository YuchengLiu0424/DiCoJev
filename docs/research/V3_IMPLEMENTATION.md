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

The LLaDA HTTP server now exposes `/v1/structured-read`. Generation and structured reads share one
loaded model process. The endpoint appends the checkpoint's diffusion mask token, validates that
every requested label maps to exactly one tokenizer token, performs one model forward pass, and
returns only the requested label logits. `LladaHTTPNativeReadRuntime` connects that endpoint to the
provider-neutral backend.

## Live runtime evidence

The first CPU-only live run completed on 2026-09-29:

- Text coverage and selection completed in 27.6 seconds. Coverage was 0.859; candidate `A` was
  selected with probability 0.9958.
- A native one-pixel PNG reached the SigLIP image processor and completed both reads in 997.9
  seconds. Coverage was 0.684; candidate `A` was selected with probability 0.9930.

The normalized evidence is stored in `benchmarks/v3_native_read.json`. These are correctness
measurements, not calibrated probabilities or an interactive performance claim. The image path
now keeps a bounded content-addressed LRU cache of projected vision features. On the same image and
prompts, total latency fell from 997.9 to 890.1 seconds (10.8%) and the logits were identical. The
coverage read populated the cache and the selection read reported a cache hit. The hit still took
412.3 seconds because the long multimodal language-model forward is repeated.

The server and runtime also support batching both masks into one multimodal forward. On this CPU
host the matched batch took 985.9 seconds: only 1.2% faster than the uncached baseline and 10.8%
slower than cached sequential reads. Coverage logits were identical; selection remained `A`, with
one logit differing by 0.015625 under batched floating-point execution. Consequently batching is
an explicit `batch_reads` / `--batch-reads` opt-in for accelerator experiments, while cached
sequential reads remain the CPU default.
