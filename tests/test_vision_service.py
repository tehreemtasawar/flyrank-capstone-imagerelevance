import json

from app.config import settings
from app import vision_service as vs


def test_mock_path_validates_and_returns_result():
    r, err, model = vs.classify_image("fox_01.jpg", "ignored")
    assert err is None and r.subject == "red fox" and model == "mock-vision"


def test_invalid_json_is_flagged_not_trusted(clean):
    (clean / "mock" / "fox_01.json").write_text("{not json")
    r, err, _ = vs.classify_image("fox_01.jpg", "x")
    assert r is None and "invalid output" in err


def test_schema_violation_is_flagged(clean):
    (clean / "mock" / "fox_01.json").write_text(json.dumps({"subject": "fox", "category": "animal", "caption": "c", "confidence": 7}))
    assert vs.classify_image("fox_01.jpg", "x")[0] is None


def test_markdown_fenced_json_is_accepted(clean):
    good = (clean / "mock" / "fox_01.json").read_text()
    (clean / "mock" / "fox_01.json").write_text("```json\n" + good + "\n```")
    assert vs.classify_image("fox_01.jpg", "x")[0].subject == "red fox"


def test_live_path_retries_then_gives_up(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "USE_MOCK_VISION", False)
    monkeypatch.setattr(vs, "_call_gemini", lambda p: (calls.append(1), "garbage")[1])
    monkeypatch.setattr(vs.time, "sleep", lambda s: None)
    r, err, _ = vs.classify_image("x.jpg", "x", on_call=lambda m, ok, n: None)
    assert r is None and len(calls) == vs.MAX_RETRIES


def test_live_path_recovers_after_bad_first_response(monkeypatch):
    good = json.dumps({"subject": "fox", "category": "animal", "attributes": [], "caption": "c", "confidence": 0.9})
    seq = iter(["garbage", good])
    monkeypatch.setattr(settings, "USE_MOCK_VISION", False)
    monkeypatch.setattr(vs, "_call_gemini", lambda p: next(seq))
    monkeypatch.setattr(vs.time, "sleep", lambda s: None)
    logged = []
    r, err, _ = vs.classify_image("x.jpg", "x", on_call=lambda m, ok, n: logged.append(ok))
    assert r is not None and logged == [False, True]
