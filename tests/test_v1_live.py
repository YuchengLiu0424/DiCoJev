"""Explicitly gated real-service smoke tests."""

import base64
import os

import pytest

from dicojev.backends import DjevLocalBackend, JevCloudBackend, LayaLocalBackend
from dicojev.generator import DiffusionGemmaGenerator, MercuryGenerator
from dicojev.schemas import Candidate, DecisionRequest, DecisionSpec, ImageRef, MultimodalState


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("DICOJEV_RUN_LIVE_DLM") != "1",
    reason="set DICOJEV_RUN_LIVE_DLM=1 with a local DiffusionGemma server",
)
async def test_live_diffusiongemma_candidate_smoke():
    spec = await DiffusionGemmaGenerator(
        base_url=os.getenv("DICOJEV_GENERATOR_URL", "http://127.0.0.1:8000")
    ).generate(DecisionRequest(state=MultimodalState(text="A draft is ready."), goal="Choose"))
    assert spec.candidates


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("DICOJEV_RUN_LIVE_DLM_IMAGE") != "1",
    reason="set DICOJEV_RUN_LIVE_DLM_IMAGE=1 with the local multimodal DLM running",
)
async def test_live_diffusiongemma_native_image_smoke():
    one_pixel_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    spec = await DiffusionGemmaGenerator(
        base_url=os.getenv("DICOJEV_GENERATOR_URL", "http://127.0.0.1:8000")
    ).generate(
        DecisionRequest(
            state=MultimodalState(
                text="Inspect this image.",
                images=(ImageRef(data=one_pixel_png, media_type="image/png"),),
            ),
            goal="Choose an appropriate next action",
        )
    )
    assert spec.candidates


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("DICOJEV_RUN_LIVE_MERCURY") != "1",
    reason="set DICOJEV_RUN_LIVE_MERCURY=1 with INCEPTION_API_KEY",
)
async def test_live_mercury_candidate_smoke():
    spec = await MercuryGenerator().generate(
        DecisionRequest(state=MultimodalState(text="A draft is ready."), goal="Choose")
    )
    assert spec.candidates


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("DICOJEV_RUN_LIVE_DJEV") != "1",
    reason="set DICOJEV_RUN_LIVE_DJEV=1 with a local Djev service",
)
async def test_live_djev_structured_read_smoke():
    candidate = Candidate(id="A", action="Review the draft")
    result = await DjevLocalBackend(
        base_url=os.getenv("DICOJEV_DJEV_URL", "http://127.0.0.1:8011")
    ).decide(
        MultimodalState(text="A draft is ready."),
        DecisionSpec(
            task="Choose",
            candidates=(candidate,),
            selection_instruction="Choose the best action",
            coverage_instruction="Is an acceptable action present?",
        ),
        [candidate, Candidate(id="N", action="None of the above", synthetic=True)],
    )
    assert result.coverage is not None and result.selection is not None


def _systemone_fixture():
    candidate = Candidate(id="A", action="Review the draft")
    return (
        MultimodalState(text="A draft is ready."),
        DecisionSpec(
            task="Choose",
            candidates=(candidate,),
            selection_instruction="Choose the best action",
            coverage_instruction="Is an acceptable action present?",
        ),
        [candidate, Candidate(id="N", action="None of the above", synthetic=True)],
    )


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("DICOJEV_RUN_LIVE_JEV") != "1",
    reason="set DICOJEV_RUN_LIVE_JEV=1 with JEV_API_KEY",
)
async def test_live_jev_structured_read_smoke():
    state, spec, candidates = _systemone_fixture()
    result = await JevCloudBackend().decide(state, spec, candidates)
    assert result.coverage is not None and result.selection is not None


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("DICOJEV_RUN_LIVE_LAYA") != "1",
    reason="set DICOJEV_RUN_LIVE_LAYA=1 with a local Laya service",
)
async def test_live_laya_structured_read_smoke():
    state, spec, candidates = _systemone_fixture()
    result = await LayaLocalBackend(
        base_url=os.getenv("DICOJEV_LAYA_URL", "http://127.0.0.1:8011")
    ).decide(state, spec, candidates)
    assert result.coverage is not None and result.selection is not None
