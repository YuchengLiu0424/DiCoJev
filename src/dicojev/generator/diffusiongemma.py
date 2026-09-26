"""OpenAI-compatible client for a separately served DiffusionGemma runtime."""

from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any

import httpx

from ..errors import GeneratorUnavailable, MalformedProviderResponse
from ..harness.core import InvalidDecisionSpec, canonical_action, parse_decision_spec
from ..schemas import DecisionRequest, DecisionSpec, LoopContext

DEFAULT_MODEL = "google/diffusiongemma-26B-A4B-it"


def _repair_trailing_commas(raw: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", raw)


class DiffusionGemmaGenerator:
    """Generate project-native DecisionSpec JSON through an HTTP model server."""

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

    def build_messages(
        self, request: DecisionRequest, context: LoopContext | None = None
    ) -> list[dict[str, str]]:
        limit = request.budget.max_candidates
        expansion = ""
        if context is not None:
            limit = min(
                context.remaining_candidate_budget,
                context.generation_feedback.requested_new_candidates,
            )
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
        schema = {
            "schema_version": "1",
            "task": "string",
            "decision_type": "choice",
            "candidates": [{"action": "string", "tool": None, "arguments_hint": {}}],
            "selection_instruction": "string",
            "coverage_instruction": "string",
            "constraints": ["string"],
        }
        user = (
            f"Observation: {request.state.text}\n"
            f"Structured state: {json.dumps(request.state.structured, ensure_ascii=False)}\n"
            f"Goal: {request.goal}\n"
            f"Available tools: {json.dumps(request.available_tools)}\n"
            f"Constraints: {json.dumps(request.constraints)}\n"
            f"History: {json.dumps(request.history)}\n"
            f"Generate at most {limit} candidates.{expansion}\n"
            f"Return exactly one JSON object matching: {json.dumps(schema)}"
        )
        return [
            {
                "role": "system",
                "content": (
                    "Generate a backend-neutral DiCoJev DecisionSpec. Return JSON only. "
                    "Never emit provider fields, probabilities, NOTA, or controller actions."
                ),
            },
            {"role": "user", "content": user},
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

    async def generate(
        self, request: DecisionRequest, context: LoopContext | None = None
    ) -> DecisionSpec:
        if request.state.images:
            raise GeneratorUnavailable("v1 generator supports text state only")
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
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise GeneratorUnavailable("DiffusionGemma service unavailable") from error
        finally:
            self.last_latency_ms = (perf_counter() - started) * 1000
        self.last_usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
        try:
            spec = parse_decision_spec(self._content(payload), _repair_trailing_commas)
        except InvalidDecisionSpec as error:
            raise MalformedProviderResponse("invalid DecisionSpec from generator") from error
        limit = request.budget.max_candidates
        if context is not None:
            limit = min(
                context.remaining_candidate_budget,
                context.generation_feedback.requested_new_candidates,
            )
            prior = {canonical_action(item.action) for item in context.prior_candidates}
            if any(canonical_action(item.action) in prior for item in spec.candidates):
                raise MalformedProviderResponse("expansion repeated a prior candidate")
        if not spec.candidates or len(spec.candidates) > limit:
            raise MalformedProviderResponse("generator violated candidate limit")
        return spec
