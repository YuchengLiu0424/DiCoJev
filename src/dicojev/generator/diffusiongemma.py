"""OpenAI-compatible client for a separately served DiffusionGemma runtime."""

from __future__ import annotations

import json
import os
import re
from time import perf_counter
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..errors import (
    CapabilityMismatch,
    ConfigurationError,
    GeneratorUnavailable,
    MalformedProviderResponse,
)
from ..harness.core import canonical_action
from ..multimodal import materialize_image
from ..schemas import Candidate, DecisionRequest, DecisionSpec, GeneratorCapabilities, LoopContext

DEFAULT_MODEL = "google/diffusiongemma-26B-A4B-it"


def _repair_trailing_commas(raw: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", raw)


class _CompactCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str = Field(min_length=1)
    tool: str | None = None
    constraint_violations: tuple[str, ...] = ()

    @field_validator("action")
    @classmethod
    def normalize_action(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("candidate action must not be empty")
        return normalized


class _CompactCandidates(BaseModel):
    """The only semantic content delegated to the language model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[str | _CompactCandidate, ...] = Field(min_length=1)

    @field_validator("candidates")
    @classmethod
    def normalize_candidates(
        cls, values: tuple[str | _CompactCandidate, ...]
    ) -> tuple[str | _CompactCandidate, ...]:
        normalized = tuple(value.strip() if isinstance(value, str) else value for value in values)
        if any(isinstance(value, str) and not value for value in normalized):
            raise ValueError("candidate actions must not be empty")
        return normalized


class OpenAICompatibleCandidateGenerator:
    """Generate project-native DecisionSpec JSON through an OpenAI-compatible server."""

    capabilities = GeneratorCapabilities(supports_images=True, supports_native_multimodal=True)
    provider_name = "DiffusionGemma"
    minimum_completion_tokens = 64
    extra_request_fields: ClassVar[dict[str, Any]] = {}
    truncate_excess_candidates = False

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8000",
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
        api_key: str | None = None,
        max_completion_tokens: int | None = None,
        max_repair_attempts: int = 1,
    ) -> None:
        if max_completion_tokens is not None and max_completion_tokens < 1:
            raise ValueError("max_completion_tokens must be positive")
        if max_repair_attempts < 0:
            raise ValueError("max_repair_attempts must not be negative")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.api_key = api_key
        self.max_completion_tokens = max_completion_tokens
        self.max_repair_attempts = max_repair_attempts
        self.last_latency_ms = 0.0
        self.last_usage: dict[str, Any] = {}
        self.last_repair_count = 0

    @staticmethod
    def _candidate_limit(request: DecisionRequest, context: LoopContext | None) -> int:
        if context is None:
            rounds = request.budget.max_expansions + 1
            return max(1, (request.budget.max_candidates + rounds - 1) // rounds)
        return min(
            context.remaining_candidate_budget,
            context.generation_feedback.requested_new_candidates,
        )

    def build_messages(
        self, request: DecisionRequest, context: LoopContext | None = None
    ) -> list[dict[str, Any]]:
        limit = self._candidate_limit(request, context)
        expansion = ""
        if context is not None:
            prior = [
                {"id": candidate.id, "action": candidate.action}
                for candidate in context.prior_candidates
            ]
            expansion = (
                "\nThis is an expansion round. Existing candidates are supplied only for "
                "comparison; do not repeat or paraphrase them. Return only new candidates.\n"
                f"Existing candidates: {json.dumps(prior, ensure_ascii=False)}\n"
                f"Typed regeneration constraint: {context.generation_feedback.instruction}\n"
            )
        user = (
            f"Observation: {request.state.text}\n"
            f"Structured state: {json.dumps(request.state.structured, ensure_ascii=False)}\n"
            f"Goal: {request.goal}\n"
            f"Available tools: {json.dumps(request.available_tools)}\n"
            f"Constraints: {json.dumps(request.constraints)}\n"
            f"History: {json.dumps(request.history)}\n"
            f"Generate at most {limit} candidates.{expansion}\n"
            "Return one JSON object with exactly one key named candidates. Its value must be "
            "an array of objects with action, optional tool, and optional constraint_violations. "
            "Use only declared tool names and copy any violated constraint exactly."
        )
        user_content: str | list[dict[str, Any]] = user
        if request.state.images:
            user_content = [{"type": "text", "text": user}]
            for image in request.state.images:
                native = materialize_image(image)
                user_content.append({"type": "image_url", "image_url": {"url": native.url}})
        return [
            {
                "role": "system",
                "content": (
                    "Generate distinct candidate actions for a decision. Return JSON only, "
                    "without analysis or markdown. Never emit probabilities, NOTA, or "
                    "controller actions."
                ),
            },
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _content(payload: dict[str, Any]) -> str:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise MalformedProviderResponse("missing chat completion content") from error
        if isinstance(content, list):
            content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
        if not isinstance(content, str) or not content.strip():
            raise MalformedProviderResponse("chat completion content is empty")
        return content

    def _chat_completions_path(self) -> str:
        return "/chat/completions" if self.base_url.endswith("/v1") else "/v1/chat/completions"

    @staticmethod
    def _repair_messages(
        messages: list[dict[str, Any]], content: str, error: MalformedProviderResponse
    ) -> list[dict[str, Any]]:
        return [
            *messages,
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": (
                    f"The response was rejected: {error}. Return a corrected JSON object only. "
                    "Use exactly one candidates array, respect its requested limit, omit candidate "
                    "IDs, and do not repeat prior actions."
                ),
            },
        ]

    @staticmethod
    def _parse_compact(content: str) -> _CompactCandidates:
        def parse(value: str) -> _CompactCandidates | None:
            decoder = json.JSONDecoder()
            for match in re.finditer(r"\{", value):
                try:
                    payload, _ = decoder.raw_decode(value[match.start() :])
                    return _CompactCandidates.model_validate(payload)
                except (json.JSONDecodeError, ValidationError):
                    continue
            return None

        compact = parse(content) or parse(_repair_trailing_commas(content))
        if compact is None:
            raise MalformedProviderResponse("invalid compact candidate response from generator")
        return compact

    @classmethod
    def parse_response(
        cls,
        content: str,
        request: DecisionRequest,
        context: LoopContext | None = None,
    ) -> DecisionSpec:
        """Validate compact model output and deterministically construct a DecisionSpec."""
        compact = cls._parse_compact(content)
        candidates = tuple(
            Candidate(action=item)
            if isinstance(item, str)
            else Candidate(
                action=item.action,
                tool=item.tool,
                constraint_violations=item.constraint_violations,
            )
            for item in compact.candidates
        )
        limit = cls._candidate_limit(request, context)
        if limit <= 0:
            raise MalformedProviderResponse("candidate budget is exhausted")
        if len(candidates) > limit:
            if cls.truncate_excess_candidates:
                candidates = candidates[:limit]
            else:
                raise MalformedProviderResponse("generator violated candidate limit")
        if context is not None:
            prior = {canonical_action(item.action) for item in context.prior_candidates}
            if any(canonical_action(item.action) in prior for item in candidates):
                raise MalformedProviderResponse("expansion repeated a prior candidate")
        constraint_text = "; ".join(request.constraints)
        constraint_suffix = f" Constraints: {constraint_text}" if constraint_text else ""
        return DecisionSpec(
            task=request.goal,
            candidates=candidates,
            selection_instruction=(
                f"Choose the candidate that best achieves this goal: {request.goal}"
                f"{constraint_suffix}"
            ),
            coverage_instruction=(
                f"Determine whether at least one candidate acceptably achieves this goal: "
                f"{request.goal}{constraint_suffix}"
            ),
            constraints=request.constraints,
        )

    async def generate(
        self, request: DecisionRequest, context: LoopContext | None = None
    ) -> DecisionSpec:
        limit = self._candidate_limit(request, context)
        started = perf_counter()
        messages = self.build_messages(request, context)
        total_usage: dict[str, Any] = {}
        self.last_repair_count = 0
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
                headers=({"Authorization": f"Bearer {self.api_key}"} if self.api_key else None),
            ) as client:
                for attempt in range(self.max_repair_attempts + 1):
                    response = await client.post(
                        self._chat_completions_path(),
                        json={
                            "model": self.model,
                            "messages": messages,
                            "response_format": {"type": "json_object"},
                            "max_tokens": min(
                                max(self.minimum_completion_tokens, 32 * limit + 32),
                                self.max_completion_tokens or 10**9,
                            ),
                            **self.extra_request_fields,
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
                    for key, value in usage.items():
                        if isinstance(value, int | float):
                            total_usage[key] = total_usage.get(key, 0) + value
                    content = self._content(payload)
                    try:
                        result = self.parse_response(content, request, context)
                        self.last_repair_count = attempt
                        return result
                    except MalformedProviderResponse as error:
                        if attempt >= self.max_repair_attempts:
                            raise
                        messages = self._repair_messages(messages, content, error)
        except (httpx.HTTPError, ValueError) as error:
            raise GeneratorUnavailable(f"{self.provider_name} service unavailable") from error
        finally:
            self.last_latency_ms = (perf_counter() - started) * 1000
            self.last_usage = total_usage

        raise MalformedProviderResponse("generator exhausted structured-output repair attempts")


class DiffusionGemmaGenerator(OpenAICompatibleCandidateGenerator):
    """DiffusionGemma candidate generator using an OpenAI-compatible runtime."""


class MercuryGenerator(OpenAICompatibleCandidateGenerator):
    """Hosted Inception Mercury text DLM through its OpenAI-compatible API."""

    capabilities = GeneratorCapabilities()
    provider_name = "Mercury"
    minimum_completion_tokens = 1000
    extra_request_fields: ClassVar[dict[str, Any]] = {
        "reasoning_effort": "low",
        "temperature": 0.2,
    }
    truncate_excess_candidates = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.inceptionlabs.ai/v1",
        model: str = "mercury-2.5",
        timeout_seconds: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        key = api_key or os.getenv("INCEPTION_API_KEY") or os.getenv("MERCURY_API_KEY")
        if not key:
            raise ConfigurationError("INCEPTION_API_KEY or MERCURY_API_KEY is required for Mercury")
        super().__init__(
            base_url=os.getenv("INCEPTION_BASE_URL", base_url),
            model=os.getenv("INCEPTION_MODEL", model),
            timeout_seconds=timeout_seconds,
            transport=transport,
            api_key=key,
        )

    async def generate(
        self, request: DecisionRequest, context: LoopContext | None = None
    ) -> DecisionSpec:
        if request.state.images:
            raise CapabilityMismatch("Mercury native image input is not declared")
        return await super().generate(request, context)
