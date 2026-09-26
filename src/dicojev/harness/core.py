"""Deterministic parsing and candidate-set preparation."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from ..schemas import Candidate, CandidateQuality, DecisionRequest, DecisionSpec


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


def _tokens(action: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", canonical_action(action)))


def _violates_explicit_constraint(action: str, constraint: str) -> bool:
    action_tokens = _tokens(action)
    constraint_tokens = re.findall(r"[a-z0-9]+", constraint.casefold())
    if constraint_tokens[:2] not in (["do", "not"], ["must", "not"]):
        return False
    rule = constraint_tokens[2:]
    if "without" in rule:
        split = rule.index("without")
        prohibited = set(rule[:split])
        required = set(rule[split + 1 :])
        return bool(prohibited) and prohibited <= action_tokens and not required <= action_tokens
    prohibited = set(rule)
    return bool(prohibited) and prohibited <= action_tokens


def evaluate_candidate_quality(
    candidates: list[Candidate], request: DecisionRequest
) -> dict[str, CandidateQuality]:
    """Compute deterministic quality flags independently of coverage evidence."""
    tools = set(request.available_tools)
    groups: dict[str, str] = {}
    token_sets: dict[str, set[str]] = {}
    for candidate in candidates:
        candidate_id = candidate.id or ""
        current = _tokens(candidate.action)
        for prior_id, prior in token_sets.items():
            union = current | prior
            similarity = len(current & prior) / len(union) if union else 1.0
            if similarity >= 0.75:
                group = groups.get(prior_id, f"redundancy:{prior_id}")
                groups[prior_id] = group
                groups[candidate_id] = group
                break
        token_sets[candidate_id] = current

    declared_constraints = set(request.constraints)
    result: dict[str, CandidateQuality] = {}
    for candidate in candidates:
        candidate_id = candidate.id or ""
        valid = bool(candidate.action.strip()) and len(candidate.action) <= 500
        valid = valid and not any(ord(character) < 32 for character in candidate.action)
        tool_available = candidate.tool is None or candidate.tool in tools
        violations = set(candidate.constraint_violations)
        declared_violation = bool(declared_constraints.intersection(violations))
        lexical_violation = any(
            _violates_explicit_constraint(candidate.action, constraint)
            for constraint in request.constraints
        )
        constraint_compliant = not declared_violation and not lexical_violation
        result[candidate_id] = CandidateQuality(
            candidate_id=candidate_id,
            syntactically_valid=valid,
            executable=valid and tool_available and constraint_compliant,
            tool_available=tool_available,
            constraint_compliant=constraint_compliant,
            redundancy_group=groups.get(candidate_id),
        )
    return result


def merge_candidate_quality(
    reference: dict[str, CandidateQuality], backend: dict[str, CandidateQuality]
) -> dict[str, CandidateQuality]:
    """Combine independent flags conservatively; neither source can erase a failure."""
    merged = dict(reference)
    for candidate_id, observed in backend.items():
        expected = merged.get(candidate_id)
        if expected is None:
            merged[candidate_id] = observed
            continue
        merged[candidate_id] = CandidateQuality(
            candidate_id=candidate_id,
            syntactically_valid=expected.syntactically_valid and observed.syntactically_valid,
            executable=expected.executable and observed.executable,
            tool_available=expected.tool_available and observed.tool_available,
            constraint_compliant=(expected.constraint_compliant and observed.constraint_compliant),
            redundancy_group=expected.redundancy_group or observed.redundancy_group,
        )
    return merged


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
