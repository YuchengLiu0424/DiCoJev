"""First-class adapter for the project-owned LLaDA-V HTTP runtime."""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from .diffusiongemma import OpenAICompatibleCandidateGenerator

DEFAULT_LLADA_MODEL = "llada-v-local"


class LladaGenerator(OpenAICompatibleCandidateGenerator):
    """Generate multimodal candidates with the local LLaDA-V server."""

    provider_name = "LLaDA-V"
    minimum_completion_tokens = 32
    extra_request_fields: ClassVar[dict[str, Any]] = {"steps": 8, "temperature": 0.2}

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8002",
        model: str = DEFAULT_LLADA_MODEL,
        timeout_seconds: float = 600,
        transport: httpx.AsyncBaseTransport | None = None,
        max_completion_tokens: int | None = 32,
        max_repair_attempts: int = 1,
    ) -> None:
        super().__init__(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            transport=transport,
            max_completion_tokens=max_completion_tokens,
            max_repair_attempts=max_repair_attempts,
        )
