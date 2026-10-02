"""Direct in-process client for applications that do not want the HTTP API."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .config import create_agent_runtime, load_config
from .intent import DLMIntentInferer, IntentDraft
from .schemas import DecisionRequest, DecisionResponse


class DirectClient:
    """Invoke an ``AgentRuntime`` directly with typed request/response objects.

    This removes the public FastAPI/JSON transport boundary. The configured generator or
    decision backend may still use its own model-service transport.
    """

    def __init__(self, runtime: Any, intent_inferer: DLMIntentInferer | None = None) -> None:
        self.runtime = runtime
        self.intent_inferer = intent_inferer

    @classmethod
    def from_config(
        cls,
        config: str | Path | Mapping[str, Any],
        **dependencies: Any,
    ) -> DirectClient:
        payload = load_config(config) if isinstance(config, (str, Path)) else dict(config)
        model = payload.get("model", {})
        inferer = DLMIntentInferer(
            base_url=model.get("base_url", "http://127.0.0.1:8002"),
            model=model.get("generator_model", "llada-v-local"),
            timeout_seconds=model.get("timeout_seconds", 600),
            transport=dependencies.get("transport"),
            api_key=(
                dependencies.get("api_key")
                or os.getenv("INCEPTION_API_KEY")
                or os.getenv("MERCURY_API_KEY")
            ),
        )
        return cls(create_agent_runtime(payload, **dependencies), inferer)

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        return await self.runtime.decide(request)

    async def infer_intent(self, context: str, history: tuple[str, ...] = ()) -> IntentDraft:
        if self.intent_inferer is None:
            raise RuntimeError("This client has no configured intent inferer.")
        return await self.intent_inferer.infer(context, history)

    def infer_intent_sync(self, context: str, history: tuple[str, ...] = ()) -> IntentDraft:
        if self.intent_inferer is None:
            raise RuntimeError("This client has no configured intent inferer.")
        return self.intent_inferer.infer_sync(context, history)

    def decide_sync(self, request: DecisionRequest) -> DecisionResponse:
        """Synchronous convenience method for desktop and ordinary script callers."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.decide(request))
        raise RuntimeError(
            "decide_sync cannot run inside an active event loop; await decide instead"
        )
