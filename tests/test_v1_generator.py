import json

import httpx
import pytest

from dicojev.errors import MalformedProviderResponse
from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import DiffusionGemmaGenerator
from dicojev.schemas import (
    Candidate,
    DecisionRequest,
    FeedbackBundle,
    FeedbackCode,
    FeedbackSignal,
    LoopContext,
    MultimodalState,
)


def completion(actions):
    compact = {"candidates": actions}
    return {
        "choices": [{"message": {"content": json.dumps(compact)}}],
        "usage": {"x": 1},
    }


@pytest.mark.asyncio
async def test_generator_consumes_typed_loop_context_without_repeating_prior_candidate():
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=completion(["Ask for approval"]))

    bundle = FeedbackBundle(
        primary=FeedbackSignal(
            code=FeedbackCode.MISSING_ACTION,
            details={"requested_new_candidates": 1},
        ),
        source_round=0,
        controller_reason_code="low_coverage",
        generation_relevant=True,
    )
    compiled = await DeterministicFeedbackCompiler().compile(bundle)
    context = LoopContext(
        round_index=1,
        prior_candidates=(Candidate(id="A", action="Review draft"),),
        latest_feedback=bundle,
        generation_feedback=compiled,
        remaining_candidate_budget=3,
        remaining_expansion_budget=0,
    )
    generator = DiffusionGemmaGenerator(transport=httpx.MockTransport(handler))
    spec = await generator.generate(
        DecisionRequest(state=MultimodalState(text="Draft ready"), goal="Choose"), context
    )
    prompt = captured[0]["messages"][1]["content"]
    assert [item.action for item in spec.candidates] == ["Ask for approval"]
    assert spec.task == "Choose"
    assert spec.constraints == ()
    assert "MISSING_ACTION" not in prompt
    assert compiled.instruction in prompt
    assert '"id": "A"' in prompt
    assert generator.last_usage == {"x": 1}
    assert generator.last_latency_ms >= 0


@pytest.mark.asyncio
async def test_generator_bounded_repair_and_invalid_json_failure():
    payload = completion(["Review"])
    payload["choices"][0]["message"]["content"] = '{"candidates":["Review",]}'
    generator = DiffusionGemmaGenerator(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    )
    request = DecisionRequest(state=MultimodalState(text="x"), goal="Choose")
    assert (await generator.generate(request)).candidates[0].action == "Review"

    broken = DiffusionGemmaGenerator(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, json={"choices": [{"message": {"content": "not json"}}]}
            )
        )
    )
    with pytest.raises(MalformedProviderResponse):
        await broken.generate(request)


def test_generator_rejects_full_spec_and_constructs_stable_fields():
    request = DecisionRequest(
        state=MultimodalState(text="x"),
        goal="Choose safely",
        constraints=("No external messages",),
    )
    spec = DiffusionGemmaGenerator.parse_response(
        'analysis first: {}\n{"candidates":["Review locally"]}', request
    )
    assert spec.task == "Choose safely"
    assert spec.constraints == ("No external messages",)
    assert "Choose safely" in spec.selection_instruction

    with pytest.raises(MalformedProviderResponse):
        DiffusionGemmaGenerator.parse_response(
            '{"candidates":["Review"],"task":"model-controlled"}', request
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        FeedbackCode.MISSING_ACTION,
        FeedbackCode.TOOL_MISMATCH,
        FeedbackCode.REDUNDANT_SET,
    ],
)
async def test_required_feedback_codes_change_generator_constraints(code):
    bundle = FeedbackBundle(
        primary=FeedbackSignal(code=code, details={"requested_new_candidates": 1}),
        source_round=0,
        controller_reason_code="fixture",
        generation_relevant=True,
    )
    compiled = await DeterministicFeedbackCompiler().compile(bundle)
    context = LoopContext(
        round_index=1,
        prior_candidates=(Candidate(id="A", action="Review"),),
        latest_feedback=bundle,
        generation_feedback=compiled,
        remaining_candidate_budget=1,
        remaining_expansion_budget=0,
    )
    prompt = DiffusionGemmaGenerator().build_messages(
        DecisionRequest(state=MultimodalState(text="x"), goal="Choose"), context
    )[1]["content"]
    assert compiled.instruction in prompt
