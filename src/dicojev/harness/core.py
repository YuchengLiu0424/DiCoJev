"""Deterministic parsing and candidate-set preparation."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from ..schemas import Candidate, DecisionRequest, DecisionSpec


class InvalidDecisionSpec(ValueError):
    pass


def extract_json_object(text: str) -> str:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            _, end = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        return text[match.start() : match.start() + end]
    raise InvalidDecisionSpec("no valid JSON object found")


def parse_decision_spec(
    raw: str | dict[str, Any], repair: Callable[[str], str] | None = None
) -> DecisionSpec:
    if isinstance(raw, dict):
        try:
            return DecisionSpec.model_validate(raw)
        except ValidationError as error:
            raise InvalidDecisionSpec(str(error)) from error

    def parse_and_validate(value: str) -> DecisionSpec:
        try:
            payload = json.loads(extract_json_object(value))
            return DecisionSpec.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, InvalidDecisionSpec) as error:
            raise InvalidDecisionSpec(str(error)) from error

    try:
        return parse_and_validate(raw)
    except InvalidDecisionSpec as first_error:
        if repair is None:
            raise
        try:
            return parse_and_validate(repair(raw))
        except InvalidDecisionSpec as error:
            raise InvalidDecisionSpec(str(error)) from first_error


def canonical_action(action: str) -> str:
    return " ".join(action.casefold().split())


@dataclass
class CandidateRegistry:
    _ids: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def _label(index: int) -> str:
        # N is permanently reserved for synthetic NOTA.
        if index >= 13:
            index += 1
        value = index + 1
        label = ""
        while value:
            value, remainder = divmod(value - 1, 26)
            label = chr(65 + remainder) + label
        return label

    def register(self, candidates: tuple[Candidate, ...], round_index: int) -> list[Candidate]:
        result: list[Candidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = canonical_action(candidate.action)
            if not key or key in seen:
                continue
            seen.add(key)
            candidate_id = self._ids.setdefault(key, self._label(len(self._ids)))
            result.append(
                candidate.model_copy(
                    update={
                        "id": candidate_id,
                        "action": candidate.action.strip(),
                        "original_action": candidate.original_action or candidate.action,
                        "generation_round": round_index,
                        "synthetic": False,
                    }
                )
            )
        return result


def merge_candidates(prior: list[Candidate], current: list[Candidate]) -> list[Candidate]:
    merged: dict[str, Candidate] = {
        canonical_action(candidate.action): candidate for candidate in prior
    }
    for candidate in current:
        merged.setdefault(canonical_action(candidate.action), candidate)
    return list(merged.values())


def validate_candidates(candidates: list[Candidate], request: DecisionRequest) -> None:
    if not candidates:
        raise InvalidDecisionSpec("candidate set is empty after normalization")
    if len(candidates) > request.budget.max_candidates:
        raise InvalidDecisionSpec("candidate set exceeds max_candidates budget")
    tools = set(request.available_tools)
    for candidate in candidates:
        if candidate.tool is not None and candidate.tool not in tools:
            raise InvalidDecisionSpec(f"candidate {candidate.id} uses unavailable tool")


def inject_nota(candidates: list[Candidate]) -> list[Candidate]:
    return [
        *candidates,
        Candidate(
            id="N",
            action="None of the above",
            synthetic=True,
            generation_round=max((item.generation_round for item in candidates), default=0),
            original_action="None of the above",
        ),
    ]


def semantic_candidates(candidates: list[Candidate]) -> list[Candidate]:
    return [candidate for candidate in candidates if not candidate.synthetic]


def validate_backend_result(
    result: object, candidates: list[Candidate], *, supports_nota: bool
) -> None:
    """Validate normalized evidence against the exact offered transport set."""
    from ..schemas import DecisionBackendResult

    if not isinstance(result, DecisionBackendResult):
        raise TypeError("backend returned an invalid result type")
    allowed_ids = {candidate.id for candidate in candidates}
    if result.selection is not None:
        observed_ids = set(result.selection.probabilities)
        if not observed_ids <= allowed_ids:
            raise ValueError("selection contains IDs not offered to the backend")
        if result.selection.selected_id == "N" and not supports_nota:
            raise ValueError("backend selected NOTA without NOTA capability")
    semantic_ids = {candidate.id for candidate in candidates if not candidate.synthetic}
    if not set(result.candidate_quality) <= semantic_ids:
        raise ValueError("candidate quality contains unknown or synthetic candidate IDs")
