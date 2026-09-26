import pytest

from dicojev.backends import MockDecisionBackend
from dicojev.controller import ThresholdRiskController
from dicojev.escalation import MockEscalationTarget
from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import FakeCandidateGenerator
from dicojev.harness import DecisionOrchestrator
from dicojev.schemas import (
    BackendCapabilities,
    CoverageScore,
    DecisionBackendResult,
    DecisionBudget,
    DecisionRequest,
    ImageRef,
    MetaAction,
    MultimodalState,
    SelectionScore,
)


def backend_result(coverage, selected, probabilities):
    return DecisionBackendResult(
        backend="mock",
        coverage=CoverageScore(raw=coverage, method="scripted_noul"),
        selection=SelectionScore(
            selected_id=selected,
            probabilities=probabilities,
            confidence_raw=probabilities[selected],
        ),
    )


@pytest.mark.asyncio
async def test_offline_expand_loop_preserves_candidates_and_ids(decision_request):
    generator = FakeCandidateGenerator([["Send now"], ["Send now", "Review recipients"]])
    backend = MockDecisionBackend(
        [
            backend_result(0.2, "N", {"A": 0.1, "N": 0.9}),
            backend_result(0.95, "B", {"A": 0.05, "B": 0.9, "N": 0.05}),
        ]
    )
    response = await DecisionOrchestrator(
        generator,
        backend,
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
    ).run(decision_request)
    assert response.action is MetaAction.ACT
    assert [(item.id, item.action) for item in response.candidates] == [
        ("A", "Send now"),
        ("B", "Review recipients"),
    ]
    assert generator.contexts[0].prior_candidates[0].id == "A"
    assert generator.contexts[0].generation_feedback.code.value == "MISSING_ACTION"
    assert [event.controller_action for event in response.trace] == [
        MetaAction.EXPAND,
        MetaAction.ACT,
    ]
    assert response.trace[0].feedback_serialized_bytes > 0
    assert set(response.trace[0].latency_ms) == {
        "generation",
        "backend",
        "feedback_compilation",
    }


@pytest.mark.asyncio
async def test_backend_and_feedback_failure_fail_closed(decision_request):
    escalation = MockEscalationTarget()
    response = await DecisionOrchestrator(
        FakeCandidateGenerator([["Review"]]),
        MockDecisionBackend([RuntimeError("offline")]),
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
        escalation,
    ).run(decision_request)
    assert response.action is MetaAction.ESCALATE
    assert response.escalation_result == "escalated"

    class BrokenCompiler:
        async def compile(self, feedback):
            raise RuntimeError("broken")

    response = await DecisionOrchestrator(
        FakeCandidateGenerator([["Review"]]),
        MockDecisionBackend([backend_result(0.1, "N", {"A": 0.1, "N": 0.9})]),
        ThresholdRiskController(),
        BrokenCompiler(),
    ).run(decision_request)
    assert response.action is MetaAction.ESCALATE
    assert "feedback_compilation_failure" in response.controller.reason_code


@pytest.mark.asyncio
async def test_candidate_budget_and_unknown_backend_id_fail_closed(decision_request):
    constrained = decision_request.model_copy(update={"budget": DecisionBudget(max_candidates=1)})
    response = await DecisionOrchestrator(
        FakeCandidateGenerator([["One", "Two"]]),
        MockDecisionBackend([]),
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
    ).run(constrained)
    assert response.action is MetaAction.ESCALATE

    response = await DecisionOrchestrator(
        FakeCandidateGenerator([["One"]]),
        MockDecisionBackend([backend_result(0.9, "X", {"X": 1.0})]),
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
    ).run(decision_request)
    assert response.action is MetaAction.ESCALATE


@pytest.mark.asyncio
async def test_capabilities_control_images_and_nota(decision_request):
    image_request = DecisionRequest(
        state=MultimodalState(images=(ImageRef(uri="memory://image"),)),
        goal="Choose",
    )
    response = await DecisionOrchestrator(
        FakeCandidateGenerator([["One"]]),
        MockDecisionBackend([]),
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
    ).run(image_request)
    assert response.action is MetaAction.ESCALATE

    backend = MockDecisionBackend([backend_result(0.9, "A", {"A": 1.0})])
    backend.capabilities = BackendCapabilities(supports_nota=False)
    response = await DecisionOrchestrator(
        FakeCandidateGenerator([["One"]]),
        backend,
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
    ).run(decision_request)
    assert response.action is MetaAction.ACT
