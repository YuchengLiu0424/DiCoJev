"""Context-only intent drafting through the configured local DLM."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Sequence

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .errors import GeneratorUnavailable, MalformedProviderResponse


class IntentDraft(BaseModel):
    """A reviewable interpretation of an unstructured user request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    constraints: tuple[str, ...] = ()
    suggested_tools: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool = False
    clarifying_question: str | None = None

    @field_validator("goal", "instruction")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class DLMIntentInferer:
    """Ask an OpenAI-compatible DLM to structure context without taking action."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 600,
        transport: httpx.AsyncBaseTransport | None = None,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.api_key = api_key

    def _path(self) -> str:
        return "/chat/completions" if self.base_url.endswith("/v1") else "/v1/chat/completions"

    @staticmethod
    def _parse(content: str) -> IntentDraft:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", content):
            try:
                payload, _ = decoder.raw_decode(content[match.start() :])
                return IntentDraft.model_validate(payload)
            except (json.JSONDecodeError, ValidationError):
                continue
        raise MalformedProviderResponse("invalid intent draft from model")

    async def infer(self, context: str, history: Sequence[str] = ()) -> IntentDraft:
        if not context.strip():
            raise ValueError("Context is required before intent can be inferred.")
        prompt = (
            "Interpret the user's unstructured context as a decision request. Do not solve it. "
            "Return one JSON object with exactly these keys: goal, instruction, constraints, "
            "suggested_tools, assumptions, confidence, needs_clarification, clarifying_question. "
            "constraints, suggested_tools, and assumptions are arrays of strings; confidence is "
            "0 to 1. Suggested tools are proposals only. If the request is genuinely ambiguous, "
            "set needs_clarification true and ask one concise question.\n\n"
            f"Recent local chat context: {json.dumps(tuple(history), ensure_ascii=False)}\n"
            f"User context: {context.strip()}"
        )
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
                headers=({"Authorization": f"Bearer {self.api_key}"} if self.api_key else None),
            ) as client:
                response = await client.post(
                    self._path(),
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "Structure intent faithfully. Return JSON only.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "response_format": {"type": "json_object"},
                        "max_tokens": 512,
                        "temperature": 0.1,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise MalformedProviderResponse("intent response content is not text")
                return self._parse(content)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            if isinstance(error, MalformedProviderResponse):
                raise
            raise GeneratorUnavailable("intent inference service unavailable") from error

    def infer_sync(self, context: str, history: Sequence[str] = ()) -> IntentDraft:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.infer(context, history))
        raise RuntimeError("infer_sync cannot run inside an active event loop; await infer instead")
