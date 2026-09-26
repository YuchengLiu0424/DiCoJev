"""Deterministic compilation of bounded feedback."""

import json

from ..schemas import FeedbackBundle, FeedbackCode, GenerationFeedback

_TEMPLATES = {
    FeedbackCode.ADEQUATE: "Preserve the current candidate set; no expansion is requested.",
    FeedbackCode.MISSING_ACTION: (
        "The current candidate set likely omits an acceptable action. Preserve existing "
        "candidates. Generate up to {count} qualitatively different alternatives. Do not "
        "paraphrase existing actions."
    ),
    FeedbackCode.AMBIGUOUS_SELECTION: (
        "Preserve existing candidates. Generate up to {count} alternatives that are "
        "materially easier to distinguish under the stated goal and constraints."
    ),
    FeedbackCode.INSUFFICIENT_INFORMATION: (
        "Do not invent missing state. Generate only an explicit information-gathering action "
        "when the available tools support it."
    ),
    FeedbackCode.TOOL_MISMATCH: (
        "Generate alternatives using only tools declared in the request. Do not repeat "
        "candidates requiring unavailable tools."
    ),
    FeedbackCode.CONSTRAINT_FAILURE: (
        "Generate alternatives that satisfy every declared constraint. Preserve compliant "
        "prior candidates and do not repeat violating actions."
    ),
    FeedbackCode.REDUNDANT_SET: (
        "Preserve distinct prior candidates. Generate up to {count} semantically diverse "
        "alternatives and do not paraphrase existing actions."
    ),
}


class DeterministicFeedbackCompiler:
    async def compile(self, feedback: FeedbackBundle) -> GenerationFeedback:
        signal = feedback.primary
        count = int(signal.details.get("requested_new_candidates", 1))
        if count < 0:
            raise ValueError("requested_new_candidates cannot be negative")
        instruction = _TEMPLATES[signal.code].format(count=count)
        serialized = feedback.model_dump_json().encode("utf-8")
        ids = {
            candidate_id
            for item in (signal, *feedback.secondary)
            for candidate_id in item.focus_candidate_ids
        }
        return GenerationFeedback(
            code=signal.code,
            instruction=instruction,
            requested_new_candidates=count if feedback.generation_relevant else 0,
            preserve_prior_candidates=True,
            serialized_bytes=len(serialized),
            referenced_candidate_count=len(ids),
            prompt_tokens=len(instruction.split()),
        )


def compiler_snapshot(feedback: FeedbackBundle) -> str:
    """Canonical representation useful for audit/snapshot tests."""
    return json.dumps(feedback.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
