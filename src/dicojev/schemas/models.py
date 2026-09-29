"""Backend-neutral v0 data contracts."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImageRef(StrictModel):
    """A bounded native image source.

    ``uri`` accepts a local path, provider-accessible reference, or data URL. ``data``
    carries in-memory bytes. Exactly one source is required.
    """

    uri: str | None = None
    data: bytes | None = Field(default=None, repr=False)
    media_type: str | None = None
    alt_text: str | None = None

    @model_validator(mode="after")
    def validate_source(self) -> ImageRef:
        if (self.uri is None) == (self.data is None):
            raise ValueError("exactly one of uri or data is required")
        if self.media_type is not None and not self.media_type.startswith("image/"):
            raise ValueError("image media_type must start with image/")
        if self.data is not None and len(self.data) > 10 * 1024 * 1024:
            raise ValueError("image bytes exceed the 10 MiB limit")
        return self


class MultimodalState(StrictModel):
    text: str = ""
    images: tuple[ImageRef, ...] = ()
    structured: dict[str, Any] = Field(default_factory=dict)


class DecisionBudget(StrictModel):
    max_candidates: int = Field(default=8, ge=1)
    max_expansions: int = Field(default=1, ge=0)
    latency_ms: float | None = Field(default=None, gt=0)
    compute_units: float | None = Field(default=None, gt=0)


class DecisionRequest(StrictModel):
    state: MultimodalState
    goal: str = Field(min_length=1)
    available_tools: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    history: tuple[str, ...] = ()
    budget: DecisionBudget = Field(default_factory=DecisionBudget)


class Candidate(StrictModel):
    id: str | None = None
    action: str = Field(min_length=1)
    tool: str | None = None
    arguments_hint: dict[str, Any] = Field(default_factory=dict)
    synthetic: bool = False
    generation_round: int = Field(default=0, ge=0)
    original_action: str | None = None
    constraint_violations: tuple[str, ...] = ()


class DecisionSpec(StrictModel):
    schema_version: Literal["1"] = "1"
    task: str = Field(min_length=1)
    decision_type: Literal["choice"] = "choice"
    candidates: tuple[Candidate, ...]
    selection_instruction: str = Field(min_length=1)
    coverage_instruction: str = Field(min_length=1)
    constraints: tuple[str, ...] = ()


class CoverageScore(StrictModel):
    raw: float = Field(ge=0, le=1)
    calibrated: float | None = Field(default=None, ge=0, le=1)
    method: str = Field(min_length=1)


class SelectionScore(StrictModel):
    selected_id: str | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence_raw: float | None = Field(default=None, ge=0, le=1)
    confidence_calibrated: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_distribution(self) -> SelectionScore:
        if any(not 0 <= value <= 1 for value in self.probabilities.values()):
            raise ValueError("selection probabilities must be in [0, 1]")
        if self.probabilities and abs(sum(self.probabilities.values()) - 1.0) > 1e-6:
            raise ValueError("selection probabilities must sum to 1")
        if self.selected_id is not None and self.selected_id not in self.probabilities:
            raise ValueError("selected_id must occur in probabilities")
        return self


class CandidateQuality(StrictModel):
    candidate_id: str
    syntactically_valid: bool = True
    executable: bool = True
    tool_available: bool = True
    constraint_compliant: bool = True
    redundancy_group: str | None = None


class GeneratorCapabilities(StrictModel):
    supports_text: bool = True
    supports_images: bool = False
    supports_native_multimodal: bool = False


class BackendCapabilities(StrictModel):
    supports_text: bool = True
    supports_images: bool = False
    supports_native_multimodal: bool = False
    supports_binary_coverage: bool = True
    supports_choice_distribution: bool = True
    supports_score: bool = True
    requires_single_token_labels: bool = False
    requires_network: bool = False
    requires_api_key: bool = False
    supports_calibrated_output: bool = False
    supports_nota: bool = True


class DecisionBackendResult(StrictModel):
    backend: str
    coverage: CoverageScore | None = None
    selection: SelectionScore | None = None
    candidate_quality: dict[str, CandidateQuality] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = Field(default=0, ge=0)


class MetaAction(str, Enum):
    ACT = "ACT"
    EXPAND = "EXPAND"
    ABSTAIN = "ABSTAIN"
    ESCALATE = "ESCALATE"


class FeedbackCode(str, Enum):
    ADEQUATE = "ADEQUATE"
    MISSING_ACTION = "MISSING_ACTION"
    AMBIGUOUS_SELECTION = "AMBIGUOUS_SELECTION"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    TOOL_MISMATCH = "TOOL_MISMATCH"
    CONSTRAINT_FAILURE = "CONSTRAINT_FAILURE"
    REDUNDANT_SET = "REDUNDANT_SET"


_ALLOWED_DETAILS = {"requested_new_candidates"}


class FeedbackSignal(StrictModel):
    code: FeedbackCode
    severity: float | None = Field(default=None, ge=0, le=1)
    focus_candidate_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    details: dict[str, int | float | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded_details(self) -> FeedbackSignal:
        unknown = set(self.details) - _ALLOWED_DETAILS
        if unknown:
            raise ValueError(f"unsupported feedback detail keys: {sorted(unknown)}")
        return self


class FeedbackBundle(StrictModel):
    primary: FeedbackSignal
    secondary: tuple[FeedbackSignal, ...] = ()
    source_round: int = Field(ge=0)
    controller_reason_code: str = Field(min_length=1)
    generation_relevant: bool

    @model_validator(mode="after")
    def compatible_signals(self) -> FeedbackBundle:
        codes = {self.primary.code, *(signal.code for signal in self.secondary)}
        if FeedbackCode.ADEQUATE in codes and len(codes) > 1:
            raise ValueError("ADEQUATE cannot be combined with problem feedback")
        if len(self.secondary) > 4:
            raise ValueError("feedback bundle is bounded to five signals")
        return self


class GenerationFeedback(StrictModel):
    code: FeedbackCode
    instruction: str = Field(min_length=1, max_length=1000)
    requested_new_candidates: int = Field(default=0, ge=0)
    preserve_prior_candidates: bool = True
    serialized_bytes: int = Field(ge=0)
    referenced_candidate_count: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)


class LoopContext(StrictModel):
    round_index: int = Field(ge=1)
    prior_candidates: tuple[Candidate, ...]
    latest_feedback: FeedbackBundle
    feedback_history: tuple[FeedbackCode, ...] = ()
    generation_feedback: GenerationFeedback
    remaining_candidate_budget: int = Field(ge=0)
    remaining_expansion_budget: int = Field(ge=0)
    remaining_latency_ms: float | None = Field(default=None, ge=0)
    remaining_compute_units: float | None = Field(default=None, ge=0)


class ControllerDecision(StrictModel):
    action: MetaAction
    reason_code: str
    feedback: FeedbackBundle
    selected_candidate_id: str | None = None


class TelemetryEvent(StrictModel):
    round_index: int = Field(ge=0)
    candidate_ids: tuple[str, ...]
    semantic_candidate_count: int = Field(ge=0)
    backend: str | None = None
    coverage_raw: float | None = Field(default=None, ge=0, le=1)
    coverage_calibrated: float | None = Field(default=None, ge=0, le=1)
    selection_raw: float | None = Field(default=None, ge=0, le=1)
    selection_calibrated: float | None = Field(default=None, ge=0, le=1)
    selected_candidate_id: str | None = None
    selection_probabilities: dict[str, float] = Field(default_factory=dict)
    feedback_codes: tuple[FeedbackCode, ...] = ()
    feedback_serialized_bytes: int = Field(default=0, ge=0)
    feedback_referenced_candidate_ids: int = Field(default=0, ge=0)
    compiled_feedback_prompt_tokens: int = Field(default=0, ge=0)
    controller_action: MetaAction
    controller_reason_code: str
    latency_ms: dict[str, float] = Field(default_factory=dict)
    compute_units: dict[str, float] = Field(default_factory=dict)
    candidate_quality: dict[str, CandidateQuality] = Field(default_factory=dict)
    remaining_candidate_budget: int = Field(default=0, ge=0)
    remaining_expansion_budget: int = Field(default=0, ge=0)
    remaining_latency_ms: float | None = Field(default=None, ge=0)
    remaining_compute_units: float | None = Field(default=None, ge=0)
    image_count: int = Field(default=0, ge=0)


class DecisionResponse(StrictModel):
    action: MetaAction
    selected_candidate: Candidate | None = None
    candidates: tuple[Candidate, ...]
    controller: ControllerDecision
    backend_result: DecisionBackendResult
    feedback: FeedbackBundle
    trace: tuple[TelemetryEvent, ...]
    total_latency_ms: float = Field(default=0, ge=0)
    total_compute_units: float = Field(default=0, ge=0)
    escalation_result: EscalationResult | None = None


class EscalationRequest(StrictModel):
    request: DecisionRequest
    candidates: tuple[Candidate, ...]
    reason_code: str


class EscalationResult(StrictModel):
    target: str = Field(min_length=1)
    status: Literal["accepted", "unavailable"]
    message: str = Field(min_length=1)
