# Evaluation Plan

This file owns the research hypotheses, benchmark design, metrics, and ablations. It does not define runtime interfaces or release sequencing.

## 1. Evaluation principle

The central experiment is not merely “which backend has the highest accuracy?” The project must measure whether candidate-set inadequacy can be detected and whether acting on that signal improves the risk–latency trade-off.

## 2. Experimental axes

### Candidate generation

Compare at least:

- direct DLM generation;
- fixed candidate count versus adaptive expansion;
- optional autoregressive generator baseline where practical.

### Decision backend

Compare:

- forced top-1 / generator self-score;
- cross-encoder ranker;
- JevCloud when available;
- DjevLocal;
- NativeDLMDecisionBackend;
- independent versus same-backbone coverage estimators where implemented.

### Input modality

Compare:

- native multimodal input;
- text-only state;
- caption-only visual reduction as an explicit baseline.

### Controller

Compare:

- always ACT;
- NOTA-only rejection;
- thresholded coverage/selection;
- fixed expansion count;
- adaptive expansion;
- fast/slow escalation.

## 3. Candidate-set stress tests

Every benchmark suite should support controlled corruption where possible:

1. remove all acceptable actions;
2. remove only the best action but retain an acceptable fallback;
3. inject plausible distractors;
4. duplicate/paraphrase one action repeatedly;
5. include impossible tool calls;
6. include constraint-violating actions;
7. vary candidate-set size;
8. perturb visual evidence while leaving text constant;
9. create ambiguous states where abstention/escalation is preferable.

The point is to measure response to candidate-set failure directly rather than infer it from aggregate task accuracy.

## 4. Ground-truth events

When an environment provides an acceptable action set `A*`:

```text
y_cov = 1[C intersects A* != empty]
y_sel = 1[selected_action in A*]
```

Where multiple actions are valid, use a set rather than artificially forcing a unique gold action.

If only environment reward is available, record the approximation used to map reward or transition success to action acceptability.

## 5. Core metrics

### Candidate construction

- candidate-set coverage;
- miscoverage;
- number of unique semantic candidates;
- invalid/non-executable rate;
- constraint violation rate;
- redundancy/diversity;
- acceptable-action rank when applicable.

### Coverage estimator

- AUROC/AUPRC for `y_cov`;
- Brier score;
- expected calibration error with explicitly stated binning;
- reliability diagram;
- false-adequate rate, especially when `y_cov = 0`;
- calibration by candidate-set size and domain.

### Selection

- conditional selection accuracy given `y_cov = 1`;
- top-1 action accuracy;
- selection Brier/ECE where probabilities are comparable;
- NOTA precision/recall;
- probability mass on unacceptable candidates.

### Controller

- end-to-end task success;
- wrong ACT rate;
- unnecessary EXPAND rate;
- successful recovery after EXPAND;
- abstention rate and selective risk;
- escalation rate and escalation utility;
- average generation rounds;
- average candidate count.

### Systems

- generation latency;
- decision-read latency;
- controller/harness latency;
- p50/p95 end-to-end latency;
- tokens/canvas steps where applicable;
- GPU memory;
- model weight duplication;
- request throughput;
- compute/cost per successful decision.

## 6. Required plots

- risk versus coverage/selective coverage;
- task risk versus end-to-end latency;
- task risk versus compute budget;
- coverage reliability diagram;
- selection reliability diagram;
- candidate-set size versus miscoverage;
- expansions versus recovered successes;
- backend latency breakdown;
- same-backbone versus independent-verifier failure correlation.

## 7. Key ablations

1. remove explicit coverage question;
2. use top-1 selection confidence as coverage proxy;
3. use NOTA probability alone;
4. remove candidate deduplication;
5. fixed candidate count versus adaptive expansion;
6. same DLM versus independent decision backend;
7. DjevLocal versus NativeDLMRead;
8. no calibration versus calibrated scores;
9. no candidate-quality features versus quality-aware controller;
10. text-only/caption-only versus native multimodal;
11. separate services versus shared DLM runtime;
12. independent generation/read passes versus safe context/runtime reuse.

## 8. Primary success criterion

The main system should improve the **risk–latency Pareto frontier** over fixed generate-then-rank baselines. A useful result is not required to dominate every baseline on raw accuracy if it provides meaningfully better behavior under candidate-set failure or compute constraints.
