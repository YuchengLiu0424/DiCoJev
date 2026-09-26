"""Offline escalation fixture."""

from .schemas import EscalationRequest, EscalationResult


class MockEscalationTarget:
    def __init__(self, response: str = "escalated", target: str = "mock") -> None:
        self.response = response
        self.target = target
        self.requests: list[EscalationRequest] = []

    async def escalate(self, request: EscalationRequest) -> EscalationResult:
        self.requests.append(request)
        return EscalationResult(target=self.target, status="accepted", message=self.response)
