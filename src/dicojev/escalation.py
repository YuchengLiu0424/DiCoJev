"""Offline escalation fixture."""

from .schemas import EscalationRequest


class MockEscalationTarget:
    def __init__(self, response: str = "escalated") -> None:
        self.response = response
        self.requests: list[EscalationRequest] = []

    async def escalate(self, request: EscalationRequest) -> str:
        self.requests.append(request)
        return self.response
