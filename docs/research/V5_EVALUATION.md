# v5 Unified Runtime and 1.0 Release Evaluation

## Runtime and API

`UnifiedLladaRuntime` binds candidate generation and native binary/categorical reads to the same
LLaDA-V endpoint and therefore the same loaded model process. It exposes combined generation/read
diagnostics and can reuse the server's bounded image-feature cache. The primary local path has no
Jev or Djev dependency.

`AgentRuntime` wraps the existing typed-feedback orchestrator. Only final `ACT` decisions cross the
new `AllowlistedToolExecutor` boundary. Unknown tools are rejected, handler failures are normalized,
and every attempted action records its result plus the structured state before and after execution.
The optional FastAPI application exposes this complete response at `POST /v1/decide`.

## Acceptance evidence

`benchmarks/v5_evaluation.json` recreates the offline release table from the 11 controlled closed-
loop cases and prior versioned live artifacts:

- 11/11 cases pass;
- controller traces contain `ACT`, `EXPAND`, `ABSTAIN`, and `ESCALATE`;
- text and native-image cases are present;
- typed feedback totals and p50/p95 harness latency are reported;
- the v4 measured risk-latency-token table is retained without changing its negative result;
- cached and uncached native-image runs preserve identical coverage and selection while the cached
  sequential path improves measured CPU latency by 10.8%;
- the offline demo executes an allowlisted tool and records the environment transition.

The runtime's 64 GB CPU host cannot provide a meaningful GPU-memory number. The report therefore
separates Python harness peak memory from the earlier live model/runtime evidence rather than
mislabeling host RAM or fabricated GPU usage.

## Research conclusion

v5 integrates the complete architecture and makes it reproducible as a 1.0 software release. It
does not overturn v4: typed feedback and adaptive compute were not superior on the five-task live
study, and native LLaDA coverage was weaker than hosted Jev. The contribution is a unified,
fail-closed experimental runtime in which those hypotheses can be measured honestly.

## Release decision

The v5 software acceptance gates pass when the full offline suite, package build/install smoke,
demo, documentation ownership check, and CI all pass. Live model artifacts remain versioned
evidence and optional integration tests remain opt-in because they require services or hardware.
