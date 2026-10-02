"""Direct in-process client for applications that do not want the HTTP API."""

from __future__ import annotations

import asyncio
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
        self.model_name = intent_inferer.model if intent_inferer else "unknown"

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
            api_key=dependencies.get("api_key"),
        )
        return cls(create_agent_runtime(payload, **dependencies), inferer)

    def configure_api_key(self, value: str | None) -> None:
        """Apply a user-provided key to compatible model clients for this process."""
        if self.intent_inferer is not None:
            self.intent_inferer.api_key = value
        orchestrator = getattr(self.runtime, "orchestrator", None)
        generator = getattr(orchestrator, "generator", None)
        nested = getattr(generator, "generator", None)
        for target in (generator, nested):
            if target is not None and hasattr(target, "api_key"):
                target.api_key = value

    def usage_snapshot(self) -> dict[str, int | float]:
        orchestrator = getattr(self.runtime, "orchestrator", None)
        generator = getattr(orchestrator, "generator", None)
        diagnostics = getattr(generator, "diagnostics", {})
        if isinstance(diagnostics, dict):
            totals = {"prompt_tokens": 0, "completion_tokens": 0}
            aliases = {
                "prompt_tokens": "prompt_tokens",
                "input_tokens": "prompt_tokens",
                "completion_tokens": "completion_tokens",
                "output_tokens": "completion_tokens",
            }

            def collect(value: Any) -> None:
                if isinstance(value, dict):
                    for key, item in value.items():
                        target = aliases.get(key)
                        if target and isinstance(item, int | float):
                            totals[target] += item
                        elif isinstance(item, dict | list | tuple):
                            collect(item)
                elif isinstance(value, list | tuple):
                    for item in value:
                        collect(item)

            collect(diagnostics)
            return {
                **totals,
                "total_tokens": totals["prompt_tokens"] + totals["completion_tokens"],
            }
        usage = getattr(generator, "last_usage", {})
        return dict(usage) if isinstance(usage, dict) else {}

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
