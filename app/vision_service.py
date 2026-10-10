"""
Vision service: turns one image file into a schema-validated VisionTagResult.

Two paths, chosen by USE_MOCK_VISION in .env:
  - Live path: sends the image to Gemini Flash with a prompt that demands
    JSON matching VisionTagResult, retries on invalid output.
  - Mock path: reads a pre-generated JSON file for that image from
    data/mock_vision/<filename>.json. This is the approach FlyRank's own
    Q&A thread approved when the free vision tier is rate-limited —
    the rest of the pipeline (schema validation, DB writes, guard) is
    identical either way, only where the JSON comes from changes.

Either way, nothing downstream ever sees an unvalidated response.
"""
import json
import os
import time
from typing import Optional, Tuple

from pydantic import ValidationError

from app.config import settings
from app.schemas import VisionTagResult

VISION_PROMPT = """You are labeling an image for a content-matching system.
Look at the image and respond with ONLY a JSON object (no markdown fences,
no extra text) with exactly these fields:

{
  "subject": "short noun phrase, e.g. 'red fox'",
  "category": "one broad category, e.g. 'animal'",
  "attributes": ["3-6 short descriptive tags"],
  "caption": "one sentence describing the image",
  "confidence": 0.0 to 1.0, how sure you are of the subject/category
}

Be conservative with confidence: if the subject is ambiguous or the image
is unclear, use a lower confidence value rather than guessing.
"""

MAX_RETRIES = 3


class VisionError(Exception):
    pass


def _call_gemini(image_path: str) -> str:
    """Raw call to Gemini Flash vision. Returns the raw text response."""
    import google.generativeai as genai

    if not settings.GEMINI_API_KEY:
        raise VisionError("GEMINI_API_KEY is not set and USE_MOCK_VISION is false")

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.GEMINI_VISION_MODEL)

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    mime_type = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
    response = model.generate_content(
        [VISION_PROMPT, {"mime_type": mime_type, "data": image_bytes}]
    )
    return response.text


def _read_mock(filename: str) -> str:
    mock_path = os.path.join(settings.MOCK_VISION_DIR, f"{os.path.splitext(filename)[0]}.json")
    if not os.path.exists(mock_path):
        raise VisionError(
            f"No mock vision file at {mock_path}. "
            f"Create one (see data/mock_vision/README.md) or set USE_MOCK_VISION=false."
        )
    with open(mock_path, "r") as f:
        return f.read()


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def classify_image(filename: str, image_path: str, on_call=None) -> Tuple[Optional[VisionTagResult], Optional[str], str]:
    """
    Returns (result, error, model_name).
    result is None if every retry failed to produce valid, schema-matching JSON —
    the caller flags the image rather than guessing.

    on_call(model_name, success, note) is invoked once per model call (including
    each retry) so the caller can attribute cost per call.
    """
    model_name = "mock-vision" if settings.USE_MOCK_VISION else settings.GEMINI_VISION_MODEL
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = _read_mock(filename) if settings.USE_MOCK_VISION else _call_gemini(image_path)
            cleaned = _strip_markdown_fence(raw)
            data = json.loads(cleaned)
            result = VisionTagResult.model_validate(data)
            if on_call:
                on_call(model_name, True, None)
            return result, None, model_name
        except (json.JSONDecodeError, ValidationError, VisionError) as e:
            last_error = f"attempt {attempt}/{MAX_RETRIES}: invalid output: {e}"
        except Exception as e:  # network / rate limit etc. — still retry
            last_error = f"attempt {attempt}/{MAX_RETRIES}: API error: {e}"
        if on_call:
            on_call(model_name, False, last_error[:200])
        if settings.USE_MOCK_VISION:
            break  # retrying a static file won't change the outcome
        time.sleep(1.5 * attempt * (4 if "429" in last_error else 1))  # back off harder on rate limits

    return None, last_error, model_name
