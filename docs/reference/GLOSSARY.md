# Glossary

**Candidate / semantic action** — an action proposed by the generator before backend selection.

**Candidate set (`C`)** — the normalized set of semantic candidates for one decision round.

**Acceptable action set (`A*`)** — evaluation-time set of next actions considered acceptable for a state/goal/tool context.

**Candidate-set coverage / adequacy** — event that `C` contains at least one member of `A*`.

**`q_cov`** — backend/model evidence estimating candidate-set adequacy.

**`q_sel`** — selection evidence/confidence for the chosen candidate relative to the supplied candidate set.

**NOTA (`N`)** — synthetic “None of the above” option used by compatible decision backends. It is evidence, not a controller meta-action.

**ACT** — execute the chosen semantic action.

**EXPAND** — generate additional semantic candidates and reevaluate.

**ABSTAIN** — take no environment action.

**ESCALATE** — transfer decision ownership to a slower/higher-authority path.

**DecisionSpec** — project-native intermediate representation generated before backend-specific compilation.

**DecisionBackend** — pluggable component that estimates coverage/selection over an existing candidate set.

**DLM** — diffusion language model; the default research family is DiffusionGemma.

**Djev** — external reference project implementing Jev-style structured reads on DiffusionGemma.
