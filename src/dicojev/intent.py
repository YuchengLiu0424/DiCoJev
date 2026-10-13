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
    options: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool = False
    clarifying_question: str | None = None

    @field_validator("goal", "instruction")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


def fallback_intent_draft(context: str) -> IntentDraft:
    """Create a conservative review-only draft when no configured DLM is reachable."""
    normalized = " ".join(context.split()).strip()
    if not normalized:
        raise ValueError("Context is required before intent can be inferred.")
    first = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0][:180]
    question = next((part.strip() for part in normalized.split("?") if part.strip()), first)
    goal = f"Clarify the requested outcome: {question[:150].rstrip('.!?')}"
    return IntentDraft(
        goal=goal,
        instruction=(
            "Ask the user to specify the desired outcome. No model interpretation is available."
        ),
        assumptions=(
            (
                "The configured DLM was unavailable, so this low-confidence draft was created "
                "locally and requires user review."
            ),
        ),
        confidence=0.25,
        needs_clarification=True,
        clarifying_question="Does the drafted goal correctly describe the outcome you want?",
    )


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
        self.last_usage: dict[str, int | float] = {}

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

    async def infer(
        self, context: str, history: Sequence[str] = (), partial_fields: dict | None = None
    ) -> IntentDraft:
        if not context.strip():
            raise ValueError("Context is required before intent can be inferred.")
        prompt = (
            "Faithfully decompose the user's task and complete missing fields. The task may be "
            "answering, calculating, writing, analyzing, planning, or choosing; do not force it "
            "into a safest-next-action goal. Preserve supplied fields verbatim. Generate concrete "
            "task-relevant candidate answers or options, not generic safety actions. "
            "Return one JSON object with exactly these keys: goal, instruction, constraints, "
            "suggested_tools, options, assumptions, confidence, needs_clarification, clarifying_question. "
            "constraints, suggested_tools, options, and assumptions are arrays of strings; confidence is "
            "0 to 1. Suggested tools are proposals only. If the request is genuinely ambiguous, "
            "set needs_clarification true and ask one concise question. Leave optional boundaries "
            "and tools empty when unnecessary; never invent tool permissions. Attached media is "
            "processed by the application later: do not list vision_model, image_analysis_tool, "
            "or other internal model capabilities as user tools.\n\n"
            f"Supplied fields: {json.dumps(partial_fields or {}, ensure_ascii=False)}\n"
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
                request_payload = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Structure intent faithfully. Return JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    # The dedicated local LLaDA server has a deliberately small bound.
                    "max_tokens": 256,
                    "temperature": 0.1,
                }
                if self.model.lower().startswith("mercury"):
                    # Mercury uses completion tokens for hidden reasoning too. With its
                    # default medium effort, a 256-token budget can end with content=null.
                    request_payload.update(max_tokens=1000, reasoning_effort="low")
                response = await client.post(self._path(), json=request_payload)
                response.raise_for_status()
                payload = response.json()
                usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
                self.last_usage = {
                    key: value for key, value in usage.items() if isinstance(value, int | float)
                }
                content = payload["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise MalformedProviderResponse("intent response content is not text")
                draft = self._parse(content)
                supplied = partial_fields or {}
                preserved = {
                    key: value
                    for key, value in supplied.items()
                    if key in {"goal", "constraints", "suggested_tools"} and value
                }
                values = {**draft.model_dump(), **preserved}
                if supplied.get("attachments") and not supplied.get("suggested_tools"):
                    values["suggested_tools"] = ()
                return IntentDraft.model_validate(values)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            if isinstance(error, MalformedProviderResponse):
                raise
            raise GeneratorUnavailable("intent inference service unavailable") from error

    def infer_sync(
        self, context: str, history: Sequence[str] = (), partial_fields: dict | None = None
    ) -> IntentDraft:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.infer(context, history, partial_fields))
        raise RuntimeError("infer_sync cannot run inside an active event loop; await infer instead")
