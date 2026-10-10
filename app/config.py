"""
Central place every other module reads settings from.
Nothing here calls any API — it just loads and exposes values from .env.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() == "true"


class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    USE_MOCK_VISION: bool = _bool("USE_MOCK_VISION")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./capstone.db")

    # Models are configurable because Google retires model names on its own schedule.
    GEMINI_VISION_MODEL: str = os.getenv("GEMINI_VISION_MODEL", "gemini-3.8-flash")
    GEMINI_EMBEDDING_MODEL: str = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")

    # "gemini" (real semantic vectors) or "local" (hash bag-of-words, plumbing/tests only).
    # Defaults to gemini when a key exists, else local. Never switches silently at runtime.
    EMBEDDING_BACKEND: str = os.getenv("EMBEDDING_BACKEND", "gemini" if os.getenv("GEMINI_API_KEY") else "local").lower()

    # Guard thresholds. 0.75 is calibrated for gemini-embedding-001 on this corpus
    # (see README "Threshold tuning" + scripts/tune_threshold.py). The local
    # fallback embedding needs ~0.12 instead.
    SIMILARITY_THRESHOLD: float = float(os.getenv(
        "SIMILARITY_THRESHOLD",
        "0.12" if (os.getenv("EMBEDDING_BACKEND") or ("gemini" if os.getenv("GEMINI_API_KEY") else "local")).lower() == "local" else "0.75",
    ))
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))

    # Batch / budget controls
    VISION_DELAY_SECONDS: float = float(os.getenv("VISION_DELAY_SECONDS", "13"))  # 5 req/min free tier
    DAILY_VISION_CALL_LIMIT: int = int(os.getenv("DAILY_VISION_CALL_LIMIT", "20"))  # budget guard (live calls/day)
    DAILY_BUDGET_USD: float = float(os.getenv("DAILY_BUDGET_USD", "0"))  # 0 = free tier only; guard stops if spend would exceed

    IMAGES_DIR: str = os.getenv("IMAGES_DIR", "data/images")
    MOCK_VISION_DIR: str = os.getenv("MOCK_VISION_DIR", "data/mock_vision")


settings = Settings()
