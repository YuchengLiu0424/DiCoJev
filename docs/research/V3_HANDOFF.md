# v3 Handoff

## Starting point

v2 closes with three verified generator paths:

- Mercury completes the bounded initial-plus-expansion controller loop and is the practical online
  default.
- Quantized DiffusionGemma completes real local CPU generation through the pinned `llama.cpp`
  runtime, but a short request takes roughly four minutes.
- LLaDA-V loads all six local shards, accepts native images, and completes both controller rounds
  through the project-owned OpenAI-compatible server. The measured rounds took roughly five and
  eight minutes on CPU.

Laya and Jev remain passing evaluator paths. Djev is retained as a hardware reference because its
patched vLLM stack does not fit the available consumer GPU. Ollama is not a supported LLaDA-V or
DiffusionGemma runtime for this release.

## v3 objectives

1. Make structured generation a runtime guarantee. Add constrained JSON decoding where the backend
   supports it, plus a bounded repair or regeneration policy for malformed, empty, redundant, or
   over-budget candidate sets.
2. Introduce a first-class LLaDA adapter. Stop routing LLaDA through a generically named local
   DiffusionGemma adapter, while preserving the common generator protocol and usage accounting.
3. Improve local latency. Measure quantization, fewer diffusion steps, prompt-prefix caching, and
   batching before choosing a supported local deployment profile. Quality and constraint adherence
   must be measured alongside speed.
4. Expand multimodal evaluation. Replace the one-pixel transport probe with a small reproducible
   suite covering visual ambiguity, text-in-image, conflicting text/image evidence, and image-free
   regressions.
5. Calibrate backend comparisons. Run identical prompts and budgets across Mercury,
   DiffusionGemma, and LLaDA, recording valid-response rate, repair count, candidate diversity,
   controller outcome, token usage, peak memory, and latency.

## Release gates proposed for v3

- At least 95% schema-valid first responses on the fixed evaluation suite; 100% after at most one
  bounded repair attempt.
- No duplicate or unsupported candidate IDs after normalization.
- The same controller semantics and budget enforcement across hosted and local adapters.
- Native-image tests against every backend advertised as multimodal.
- A documented default deployment and explicit fallback order when Mercury is unavailable.
- Reproducible benchmark artifacts containing environment metadata but no credentials or raw secret
  bearing provider envelopes.

## Recommended first milestone

Build the native LLaDA adapter and shared structured-output repair layer first. That isolates
backend-specific prompting from controller logic and turns the slow-but-working local model into a
reliable fallback before performance tuning begins.
