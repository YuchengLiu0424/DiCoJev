"""Text-only DiffusionGemma + Jev/Djev end-to-end example."""

import argparse
import asyncio
import os

from dicojev.backends import DjevLocalBackend, JevCloudBackend, LayaLocalBackend
from dicojev.controller import ThresholdRiskController
from dicojev.feedback import DeterministicFeedbackCompiler
from dicojev.generator import DEFAULT_MODEL, DiffusionGemmaGenerator
from dicojev.harness import DecisionOrchestrator
from dicojev.schemas import DecisionRequest, MultimodalState


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("djev", "jev", "laya"), default="djev")
    parser.add_argument("--generator-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--generator-model", default=os.getenv("DICOJEV_GENERATOR_MODEL", DEFAULT_MODEL)
    )
    parser.add_argument("--djev-url", default="http://127.0.0.1:8011")
    parser.add_argument("--laya-url", default="http://127.0.0.1:8011")
    args = parser.parse_args()
    if args.backend == "djev":
        backend = DjevLocalBackend(base_url=args.djev_url)
    elif args.backend == "laya":
        backend = LayaLocalBackend(base_url=args.laya_url)
    else:
        backend = JevCloudBackend(
            api_key=os.getenv("JEV_API_KEY"),
            base_url=os.getenv("JEV_BASE_URL", "https://api.typesafe.ai"),
            model=os.getenv("JEV_MODEL", "jev-latest"),
        )
    response = await DecisionOrchestrator(
        DiffusionGemmaGenerator(
            base_url=args.generator_url,
            model=args.generator_model,
            timeout_seconds=600,
        ),
        backend,
        ThresholdRiskController(),
        DeterministicFeedbackCompiler(),
    ).run(
        DecisionRequest(
            state=MultimodalState(text="A draft email is ready; recipients are not verified."),
            goal="Choose the safest useful next action",
        )
    )
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
