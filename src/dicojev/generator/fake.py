"""Scripted offline candidate generator."""

from collections.abc import Iterable

from ..schemas import Candidate, DecisionRequest, DecisionSpec, GeneratorCapabilities, LoopContext


class FakeCandidateGenerator:
    capabilities = GeneratorCapabilities(supports_images=True, supports_native_multimodal=True)

    def __init__(self, rounds: Iterable[Iterable[Candidate | str]]) -> None:
        self._rounds = [tuple(items) for items in rounds]
        if not self._rounds:
            raise ValueError("at least one scripted round is required")
        self.contexts: list[LoopContext] = []

    async def generate(
        self, request: DecisionRequest, context: LoopContext | None = None
    ) -> DecisionSpec:
        if context is not None:
            self.contexts.append(context)
        index = 0 if context is None else context.round_index
        if index >= len(self._rounds):
            raise RuntimeError("no scripted generator round remains")
        candidates = tuple(
            item if isinstance(item, Candidate) else Candidate(action=item)
            for item in self._rounds[index]
        )
        return DecisionSpec(
            task=request.goal,
            candidates=candidates,
            selection_instruction="Choose the safest useful next action toward the goal.",
            coverage_instruction=(
                "Determine whether at least one candidate is acceptable as the next action."
            ),
            constraints=request.constraints,
        )
