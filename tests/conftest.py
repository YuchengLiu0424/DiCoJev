import pytest

from dicojev.schemas import DecisionRequest, MultimodalState


@pytest.fixture
def decision_request() -> DecisionRequest:
    return DecisionRequest(
        state=MultimodalState(text="A draft email is ready."),
        goal="Choose the safest next action",
        available_tools=("ui.click",),
        constraints=("Do not send without review",),
    )
