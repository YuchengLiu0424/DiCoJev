import pytest
from pydantic import ValidationError

from dicojev.schemas import (
    CoverageScore,
    FeedbackBundle,
    FeedbackCode,
    FeedbackSignal,
    SelectionScore,
)


def test_raw_and_calibrated_are_distinct_and_nullable():
    coverage = CoverageScore(raw=0.8, method="fixture")
    selection = SelectionScore(
        selected_id="A", probabilities={"A": 0.8, "N": 0.2}, confidence_raw=0.8
    )
    assert coverage.calibrated is None
    assert selection.confidence_calibrated is None


@pytest.mark.parametrize("code", list(FeedbackCode))
def test_every_feedback_code_validates(code):
    assert FeedbackSignal(code=code).code is code


def test_unknown_feedback_code_and_unbounded_details_fail():
    with pytest.raises(ValidationError):
        FeedbackSignal(code="UNKNOWN")
    with pytest.raises(ValidationError):
        FeedbackSignal(code=FeedbackCode.MISSING_ACTION, details={"reasoning": 1})


def test_incompatible_feedback_bundle_fails():
    with pytest.raises(ValidationError):
        FeedbackBundle(
            primary=FeedbackSignal(code=FeedbackCode.ADEQUATE),
            secondary=(FeedbackSignal(code=FeedbackCode.MISSING_ACTION),),
            source_round=0,
            controller_reason_code="bad",
            generation_relevant=True,
        )


def test_malformed_probabilities_fail():
    with pytest.raises(ValidationError):
        SelectionScore(selected_id="A", probabilities={"A": 0.9, "N": 0.9})
