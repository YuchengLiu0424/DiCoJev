# Related Work and Novelty Boundaries

This file owns comparisons to prior systems and the boundaries of novelty claims. The project description may summarize these comparisons but should point here for citation-level detail.

## 1. Jev-style structured decision models

Jev exposes typed `choice`, `score`, and `noul` questions. Each question includes `type`, `instructions`, and type-specific `criteria`; choice returns probabilities/confidence and noul returns a yes-probability. This is a strong reference for software-oriented structured decision APIs.

Relevant source: https://jevmodel.net/docs

**Relationship to this project:** Jev assumes the caller supplies the question/options. Diffusion Decision adds open candidate construction and models uncertainty about whether the generated option set is sufficient.

## 2. Djev / diffusion structured reads

Djev implements Jev-style `/v1/systemone` decisions over DiffusionGemma. Its structured-read mechanism uses seeded canvases, pinned positions, read-only diffusion, and answer-slot log probabilities; current documentation also describes image input. Choice labels are constrained by tokenization in the structured answer template.

Relevant source: https://github.com/mmastrac/djev

**Relationship to this project:** Djev is a reference backend and technical precedent for native diffusion structured reads. `DLM generator + Djev` is explicitly a two-diffusion-stage baseline. The project later owns its structured-read implementation and studies shared-runtime coupling.

## 3. DiffusionGemma

Google introduced DiffusionGemma as an experimental 26B MoE diffusion model aimed at fast text generation. The current model distribution supports image-text-to-text usage and local serving paths, including Transformers/vLLM documentation.

Relevant sources:

- https://blog.google/innovation-and-ai/technology/developers-tools/diffusion-gemma-faster-text-generation/
- https://huggingface.co/google/diffusiongemma-26B-A4B-it

**Relationship to this project:** DiffusionGemma is the default research backbone, not an architectural hard dependency.

## 4. Generate → rank / verify → select

Candidate generation followed by specialized ranking or verification is a mature pattern. CHASE-SQL, for example, generates SQL through multiple reasoning paths and uses a dedicated candidate selection model.

Relevant source: https://arxiv.org/abs/2410.01943

**Novelty boundary:** the project must never claim that “generator + selector” is new. Its question is whether set adequacy can be explicitly separated from within-set selection and used for compute/risk control.

## 5. Selective generation and None of the Above

Ren et al., *Self-Evaluation Improves Selective Generation in Large Language Models*, study self-evaluation and explicitly add a “None of the Above” candidate to avoid forced selection among poor sampled answers.

Relevant source: https://proceedings.mlr.press/v239/ren23a.html

**Novelty boundary:** NOTA is not a project contribution by itself. Here it is one observable inside a broader candidate-set adequacy and controller design.

## 6. Conformal Language Modeling

Conformal Language Modeling studies candidate-set construction and stopping with statistical coverage guarantees so that a generated set contains at least one acceptable output with controlled miscoverage.

Relevant source: https://proceedings.iclr.cc/paper_files/paper/2024/hash/31421b112e5f7faf4fc577b74e45dab2-Abstract-Conference.html

**Novelty boundary:** candidate coverage is not a new concept. The research opportunity is fast runtime adequacy estimation and adaptive routing for multimodal DLM agents, plus comparison to conformal/repeated-generation baselines.

## 7. Online Decision Making with Generative Action Sets

Xu et al., ICLR 2026, study online agents that can pay a cost to create new actions and derive regret guarantees for balancing action selection and action generation.

Relevant source: https://proceedings.iclr.cc/paper_files/paper/2026/hash/07ed3b22786bd8d46a3654d5325bca09-Abstract-Conference.html

**Novelty boundary:** dynamic action generation and the decision to create more actions are not new in the abstract. The project is a systems/modeling contribution at the intersection of multimodal DLMs, structured reads, set adequacy, calibration, and latency-aware routing.

## 8. Positioning statement

The safest claim is:

> Existing structured decision models are efficient when the decision space is supplied; existing generate-rank systems construct candidates but typically evaluate candidates relative to the generated pool; existing selective/conformal/generative-action-set work addresses rejection, set coverage, or action creation from complementary perspectives. Diffusion Decision studies a fast multimodal DLM architecture in which the model constructs the action set, separately estimates set adequacy and conditional selection, and uses those signals to control execution versus additional computation.

## 9. Claims requiring experimental proof

The repository must treat the following as hypotheses until benchmarks support them:

- diffusion structured read is faster than a cross-encoder for the target workload;
- same-backbone generation/read is better calibrated than independent models;
- shared runtime/context materially reduces end-to-end latency;
- `q_cov * q_sel` approximates task success;
- multimodal DLM candidate generation improves over autoregressive alternatives;
- adaptive expansion dominates fixed-`K` generation across domains.
