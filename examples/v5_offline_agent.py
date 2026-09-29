"""Fresh-install v5 demo: decide, execute an allowlisted tool, and print the transition."""

from __future__ import annotations

import asyncio
import json

from dicojev.backends import MockDecisionBackend
from dicojev.controller import ThresholdRiskController
from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import FakeCandidateGenerator
from dicojev.harness import DecisionOrchestrator
from dicojev.runtime import AgentRuntime, AllowlistedToolExecutor
from dicojev.schemas import (
    Candidate,
    CoverageScore,
    DecisionBackendResult,
    DecisionRequest,
    MultimodalState,
    SelectionScore,
)


async def run_demo():
    """Run the self-contained v5 action loop and return its typed response."""
    candidate = Candidate(
        action="Record approval", tool="record", arguments_hint={"approved": True}
    )
    evidence = DecisionBackendResult(
        backend="offline-demo",
        coverage=CoverageScore(raw=0.95, method="fixture"),
        selection=SelectionScore(
            selected_id="A", probabilities={"A": 0.95, "N": 0.05}, confidence_raw=0.95
        ),
    )

    async def record(state, arguments):
        after = state.model_copy(update={"structured": {**state.structured, **arguments}})
        return {"recorded": True}, after

    runtime = AgentRuntime(
        DecisionOrchestrator(
            FakeCandidateGenerator([[candidate]]),
            MockDecisionBackend([evidence]),
            ThresholdRiskController(),
            DeterministicFeedbackCompiler(),
        ),
        AllowlistedToolExecutor({"record": record}),
    )
    return await runtime.decide(
        DecisionRequest(
            state=MultimodalState(text="Approval received", structured={"approved": False}),
            goal="Record the approval",
            available_tools=("record",),
        )
    )


async def main() -> None:
    response = await run_demo()
    print(json.dumps(response.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
