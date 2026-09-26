"""Run with: python examples/offline_feedback_loop.py"""

import asyncio
import json

from dicojev.backends import MockDecisionBackend
from dicojev.controller import ThresholdRiskController
from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import FakeCandidateGenerator
from dicojev.harness import DecisionOrchestrator
from dicojev.schemas import (
    CoverageScore,
    DecisionBackendResult,
    DecisionRequest,
    MultimodalState,
    SelectionScore,
)


def result(coverage, selected, probabilities):
    return DecisionBackendResult(
        backend="mock",
        coverage=CoverageScore(raw=coverage, method="scripted_noul"),
        selection=SelectionScore(
            selected_id=selected,
            probabilities=probabilities,
            confidence_raw=probabilities[selected],
        ),
    )


async def main() -> None:
    request = DecisionRequest(
        state=MultimodalState(text="A draft email is ready."),
        goal="Choose the safest next action",
    )
    response = await DecisionOrchestrator(
        FakeCandidateGenerator([["Send now"], ["Send now", "Review recipients"]]),
        MockDecisionBackend(
            [
                result(0.2, "N", {"A": 0.1, "N": 0.9}),
                result(0.95, "B", {"A": 0.05, "B": 0.9, "N": 0.05}),
            ]
        ),
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
    ).run(request)
    print(json.dumps(response.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
