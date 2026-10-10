import pytest
from pydantic import ValidationError

from app.schemas import PostCreate, VisionTagResult

OK = {"subject": "red fox", "category": "animal", "attributes": ["orange fur"], "caption": "A red fox", "confidence": 0.94}


def test_valid_vision_result_parses():
    assert VisionTagResult.model_validate(OK).confidence == 0.94


@pytest.mark.parametrize("patch", [
    {"confidence": None}, {"confidence": 1.5}, {"confidence": -0.1}, {"subject": ""}, {"caption": ""},
    {"category": ""}, {"confidence": "high"}, {"attributes": "not-a-list"},
])
def test_invalid_vision_results_rejected(patch):
    data = {**OK, **patch}
    if patch.get("confidence") is None and "confidence" in patch:
        data.pop("confidence")
    with pytest.raises(ValidationError):
        VisionTagResult.model_validate(data)


def test_attributes_capped():
    assert len(VisionTagResult.model_validate({**OK, "attributes": [str(i) for i in range(50)]}).attributes) == 10


def test_post_blank_rejected():
    with pytest.raises(ValidationError):
        PostCreate(title="   ", body="x")
