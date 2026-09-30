from pathlib import Path

import httpx
import pytest

from dicojev.api import create_app
from dicojev.backends import MockDecisionBackend
from dicojev.config import create_agent_runtime, load_config
from dicojev.controller import ThresholdRiskController
from dicojev.errors import ConfigurationError
from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import FakeCandidateGenerator
from dicojev.harness import DecisionOrchestrator
from dicojev.runtime import AgentRuntime, AllowlistedToolExecutor, UnifiedLladaRuntime
from dicojev.schemas import (
    Candidate,
    CoverageScore,
    DecisionBackendResult,
    DecisionBudget,
    DecisionRequest,
    FeedbackCode,
    MultimodalState,
    SelectionScore,
)
from dicojev.v4 import FeedbackRecoveryPolicy, RecoveryObservation


def test_api_cli_has_safe_local_defaults():
    from dicojev.cli import PACKAGED_DEFAULT_CONFIG, build_parser

    args = build_parser().parse_args([])
    assert Path(args.config) == PACKAGED_DEFAULT_CONFIG
    assert load_config(args.config) == load_config(
        Path(__file__).parents[1] / "configs/default.yaml"
    )
    assert args.host == "127.0.0.1"
    assert args.port == 8080


def result(coverage: float, selected: str = "A") -> DecisionBackendResult:
    return DecisionBackendResult(
        backend="fixture",
        coverage=CoverageScore(raw=coverage, method="fixture"),
        selection=SelectionScore(
            selected_id=selected,
            probabilities={"A": 0.9, "N": 0.1},
            confidence_raw=0.9,
        ),
    )


def runtime_for(candidate: Candidate, coverage: float = 0.9, executor=None) -> AgentRuntime:
    orchestrator = DecisionOrchestrator(
        FakeCandidateGenerator([[candidate]]),
        MockDecisionBackend([result(coverage)]),
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
    )
    return AgentRuntime(orchestrator, executor)


@pytest.mark.asyncio
async def test_agent_runtime_executes_allowlisted_tool_and_records_transition():
    async def update(state, arguments):
        return {"saved": arguments["value"]}, state.model_copy(
            update={"structured": {"value": arguments["value"]}}
        )

    candidate = Candidate(action="save value", tool="save", arguments_hint={"value": 7})
    runtime = runtime_for(candidate, executor=AllowlistedToolExecutor({"save": update}))
    response = await runtime.decide(
        DecisionRequest(
            state=MultimodalState(structured={"value": 0}),
            goal="save",
            available_tools=("save",),
        )
    )
    assert response.action.value == "ACT"
    assert response.execution_trace[0].action.status == "executed"
    assert response.execution_trace[0].action.result == {"saved": 7}
    assert response.execution_trace[0].state_before == {"value": 0}
    assert response.execution_trace[0].state_after == {"value": 7}


@pytest.mark.asyncio
async def test_executor_rejects_unallowlisted_tool_and_non_act_never_executes():
    executor = AllowlistedToolExecutor({})
    candidate = Candidate(action="delete", tool="shell")
    rejected = await runtime_for(candidate, executor=executor).decide(
        DecisionRequest(state=MultimodalState(), goal="delete", available_tools=("shell",))
    )
    assert rejected.execution_trace[0].action.status == "rejected"
    assert rejected.execution_trace[0].action.error_code == "tool_not_allowlisted"

    abstained = await runtime_for(candidate, coverage=0.1, executor=executor).decide(
        DecisionRequest(
            state=MultimodalState(),
            goal="delete",
            available_tools=("shell",),
            budget=DecisionBudget(max_expansions=0),
        )
    )
    assert abstained.action.value == "ABSTAIN"
    assert abstained.execution_trace == ()


def test_unified_llada_runtime_uses_one_endpoint_for_generation_and_reads():
    runtime = UnifiedLladaRuntime(base_url="http://shared:8002", batch_reads=True)
    assert runtime.generator.base_url == "http://shared:8002"
    assert runtime.reader.base_url == "http://shared:8002"
    assert runtime.supports_batch_reads is True
    assert runtime.decision_backend().runtime is runtime


def test_v5_factory_requires_fitted_policy_and_reuses_injected_runtime():
    config = {
        "model": {"deployment": "unified_local_runtime"},
        "controller": {"policy": "adaptive_compute"},
    }
    shared = UnifiedLladaRuntime(base_url="http://shared:8002")
    with pytest.raises(ConfigurationError, match="fitted feedback_policy"):
        create_agent_runtime(config, unified_runtime=shared)
    policy = FeedbackRecoveryPolicy.fit(
        [RecoveryObservation(FeedbackCode.MISSING_ACTION, True, 10)]
    )
    agent = create_agent_runtime(config, unified_runtime=shared, feedback_policy=policy)
    assert agent.orchestrator.generator is shared
    assert agent.orchestrator.backend.runtime is shared


def test_shipped_v5_config_is_constructible_without_learned_policy():
    config = load_config(Path(__file__).parents[1] / "configs/default.yaml")
    shared = UnifiedLladaRuntime(base_url="http://shared:8002")
    agent = create_agent_runtime(config, unified_runtime=shared)
    assert isinstance(agent.orchestrator.controller, ThresholdRiskController)


@pytest.mark.asyncio
async def test_v1_decide_api_exposes_full_response_trace():
    pytest.importorskip("fastapi")
    runtime = runtime_for(Candidate(action="wait"))
    app = create_app(runtime)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        response = await client.post(
            "/v1/decide",
            json={"state": {"text": "x"}, "goal": "wait"},
        )
    assert health.json() == {"status": "ok", "milestone": "v5"}
    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "ACT"
    assert payload["trace"][0]["controller_action"] == "ACT"
    assert payload["execution_trace"][0]["action"]["status"] == "not_requested"
