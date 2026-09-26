import json

import pytest

from dicojev.harness import (
    CandidateRegistry,
    InvalidDecisionSpec,
    compile_coverage,
    compile_selection,
    inject_nota,
    parse_decision_spec,
    semantic_candidates,
    validate_backend_result,
)
from dicojev.schemas import Candidate, DecisionBackendResult, DecisionSpec, SelectionScore


def _spec(candidates):
    return DecisionSpec(
        task="Choose",
        candidates=tuple(candidates),
        selection_instruction="Select one",
        coverage_instruction="Is any acceptable?",
    )


def test_json_extraction_and_one_bounded_repair():
    payload = _spec([Candidate(action="Review")]).model_dump_json()
    assert parse_decision_spec(f"prose ```json\n{payload}\n```").task == "Choose"
    calls = 0

    def repair(_raw):
        nonlocal calls
        calls += 1
        return payload

    assert parse_decision_spec("broken", repair).task == "Choose"
    assert calls == 1
    with pytest.raises(InvalidDecisionSpec):
        parse_decision_spec("broken", lambda _: "still broken")


def test_dedupe_and_stable_ids_across_expansion():
    registry = CandidateRegistry()
    first = registry.register((Candidate(action=" Review draft "), Candidate(action="review draft")), 0)
    second = registry.register((Candidate(action="Review draft"), Candidate(action="Ask approval")), 1)
    assert [item.id for item in first] == ["A"]
    assert [item.id for item in second] == ["A", "B"]


def test_candidate_labels_reserve_n_for_nota():
    registry = CandidateRegistry()
    candidates = registry.register(tuple(Candidate(action=f"action {i}") for i in range(15)), 0)
    assert "N" not in {item.id for item in candidates}


def test_empty_set_is_invalid(decision_request):
    from dicojev.harness.core import validate_candidates

    with pytest.raises(InvalidDecisionSpec):
        validate_candidates([], decision_request)


def test_synthetic_nota_excluded_from_semantic_candidates():
    candidates = [Candidate(id="A", action="Review")]
    with_nota = inject_nota(candidates)
    assert with_nota[-1].id == "N" and with_nota[-1].synthetic
    assert semantic_candidates(with_nota) == candidates


def test_exact_jev_compiler_snapshots(decision_request):
    spec = _spec([Candidate(action="Review")])
    candidates = inject_nota([Candidate(id="A", action="Review")])
    coverage = compile_coverage(decision_request, spec, candidates)
    selection = compile_selection(decision_request, spec, candidates)
    assert json.dumps(coverage, sort_keys=True) == (
        '{"context": "A draft email is ready.\\nGoal: Choose the safest next action\\n'
        'Constraints: Do not send without review", "options": ["A: Review"], '
        '"question": "Is any acceptable?", "type": "noul"}'
    )
    assert json.dumps(selection, sort_keys=True) == (
        '{"context": "A draft email is ready.\\nGoal: Choose the safest next action\\n'
        'Constraints: Do not send without review", "options": {"A": "Review", '
        '"N": "None of the above"}, "question": "Select one", "type": "choice"}'
    )


def test_provider_fields_cannot_leak_into_spec():
    payload = _spec([Candidate(action="Review")]).model_dump()
    payload["jev_model"] = "forbidden"
    with pytest.raises(InvalidDecisionSpec):
        parse_decision_spec(payload)


def test_backend_result_rejects_unoffered_ids():
    result = DecisionBackendResult(
        backend="mock",
        selection=SelectionScore(selected_id="X", probabilities={"X": 1.0}, confidence_raw=1.0),
    )
    with pytest.raises(ValueError, match="not offered"):
        validate_backend_result(result, [Candidate(id="A", action="Review")], supports_nota=True)
