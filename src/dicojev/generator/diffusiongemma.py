"""OpenAI-compatible client for a separately served DiffusionGemma runtime."""

from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..errors import GeneratorUnavailable, MalformedProviderResponse
from ..harness.core import canonical_action
from ..multimodal import materialize_image
from ..schemas import Candidate, DecisionRequest, DecisionSpec, GeneratorCapabilities, LoopContext

DEFAULT_MODEL = "google/diffusiongemma-26B-A4B-it"


def _repair_trailing_commas(raw: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", raw)


class _CompactCandidates(BaseModel):
    """The only semantic content delegated to the language model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[str, ...] = Field(min_length=1)

    @field_validator("candidates")
    @classmethod
    def normalize_candidates(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("candidate actions must not be empty")
        return normalized


class DiffusionGemmaGenerator:
    """Generate project-native DecisionSpec JSON through an HTTP model server."""

    capabilities = GeneratorCapabilities(supports_images=True, supports_native_multimodal=True)

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8000",
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.last_latency_ms = 0.0
        self.last_usage: dict[str, Any] = {}

    @staticmethod
    def _candidate_limit(request: DecisionRequest, context: LoopContext | None) -> int:
        if context is None:
            return request.budget.max_candidates
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
            "Return one JSON object with exactly one key named candidates. "
            "Its value must be an array of concise action strings."
        )
        user_content: str | list[dict[str, Any]] = user
        if request.state.images:
            user_content = [{"type": "text", "text": user}]
            for image in request.state.images:
                native = materialize_image(image)
                user_content.append(
                    {"type": "image_url", "image_url": {"url": native.url}}
                )
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
        candidates = tuple(Candidate(action=action) for action in compact.candidates)
        limit = cls._candidate_limit(request, context)
        if context is not None:
            prior = {canonical_action(item.action) for item in context.prior_candidates}
            if any(canonical_action(item.action) in prior for item in candidates):
                raise MalformedProviderResponse("expansion repeated a prior candidate")
        if len(candidates) > limit:
            raise MalformedProviderResponse("generator violated candidate limit")
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
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": self.build_messages(request, context),
                        "response_format": {"type": "json_object"},
                        "max_tokens": max(64, 32 * limit + 32),
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise GeneratorUnavailable("DiffusionGemma service unavailable") from error
        finally:
            self.last_latency_ms = (perf_counter() - started) * 1000
        self.last_usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
        return self.parse_response(self._content(payload), request, context)
