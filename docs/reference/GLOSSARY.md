# Glossary

**DiCoJev** — project name for coverage-aware Jev-style decision making over diffusion-generated action sets.

**Candidate / semantic action** — an action proposed by the generator before backend selection.

**Candidate set (`C`)** — normalized semantic candidates for one decision round.

**Acceptable action set (`A*`)** — evaluation-time set of acceptable next actions for a state/goal/tool context.

**Candidate-set coverage / adequacy** — event that `C` contains at least one member of `A*`.

**`q_cov`** — backend/model evidence estimating candidate-set adequacy.

**`q_sel`** — selection evidence/confidence for the chosen candidate relative to the supplied set.

**NOTA (`N`)** — synthetic “None of the above” backend option; evidence, not a controller action.

**FeedbackCode** — small typed reason describing why the current decision state is adequate or deficient.

**FeedbackSignal / FeedbackBundle** — bounded structured feedback emitted by controller policy from normalized evidence.

**FeedbackCompiler** — deterministic component that translates typed feedback into generator-facing regeneration constraints.

**LoopContext** — backend-neutral state carried between candidate-generation rounds, including prior candidates, feedback, and remaining budgets.

**ACT** — execute the selected semantic action.

**EXPAND** — request additional semantic candidates and reevaluate.

**ABSTAIN** — take no environment action.

**ESCALATE** — transfer decision ownership to a slower/higher-authority path.

**DecisionSpec** — project-native intermediate representation generated before backend-specific compilation.

**DecisionBackend** — pluggable component that estimates coverage/selection over an existing candidate set.

**DLM** — diffusion language model; default research family is DiffusionGemma.

**Djev** — external reference project implementing Jev-style structured reads on DiffusionGemma.
