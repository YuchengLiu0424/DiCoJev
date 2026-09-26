"""Pure Jev-compatible request compilation (no network adapter)."""

from typing import Any

from ..schemas import Candidate, DecisionRequest, DecisionSpec


def _state_text(request: DecisionRequest) -> str:
    parts = [request.state.text, f"Goal: {request.goal}"]
    if request.constraints:
        parts.append("Constraints: " + "; ".join(request.constraints))
    return "\n".join(part for part in parts if part)


def compile_coverage(
    request: DecisionRequest, spec: DecisionSpec, candidates: list[Candidate]
) -> dict[str, Any]:
    semantic = [candidate for candidate in candidates if not candidate.synthetic]
    return {
        "type": "noul",
        "context": _state_text(request),
        "question": spec.coverage_instruction,
        "options": [f"{candidate.id}: {candidate.action}" for candidate in semantic],
    }


def compile_selection(
    request: DecisionRequest, spec: DecisionSpec, candidates: list[Candidate]
) -> dict[str, Any]:
    return {
        "type": "choice",
        "context": _state_text(request),
        "question": spec.selection_instruction,
        "options": {candidate.id: candidate.action for candidate in candidates},
    }
