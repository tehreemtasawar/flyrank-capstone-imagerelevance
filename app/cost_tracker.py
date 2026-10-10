"""
Per-call cost tracking + budget guard. Every vision or embedding call — mocked
or live, successful or failed — writes one CostLog row. At free-tier usage the
cost is $0.00, but the row proves every call is attributed (Probe 6) and lets
the budget guard count today's live calls.
"""
import datetime

from sqlalchemy.orm import Session

from app.models import CostLog

# Flat per-call estimates (USD). The free tier has no billing API to query.
# Unknown models default to 0.0 — update here if you move to a paid tier.
PRICES_USD = {"mock-vision": 0.0, "local-hash-embedding": 0.0}

MOCK_MODELS = {"mock-vision", "local-hash-embedding"}


def log_cost(db: Session, call_type: str, ref_table: str, ref_id: int, model_name: str,
             success: bool = True, note: str = None) -> CostLog:
    entry = CostLog(
        call_type=call_type, ref_table=ref_table, ref_id=ref_id, model_name=model_name,
        estimated_cost_usd=PRICES_USD.get(model_name, 0.0), success=success, note=note,
    )
    db.add(entry)
    db.commit()
    return entry


def live_vision_calls_today(db: Session) -> int:
    start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(CostLog)
        .filter(CostLog.call_type == "vision", CostLog.model_name != "mock-vision", CostLog.created_at >= start)
        .count()
    )


def spend_today_usd(db: Session) -> float:
    from sqlalchemy import func
    start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    total = db.query(func.coalesce(func.sum(CostLog.estimated_cost_usd), 0.0)).filter(CostLog.created_at >= start).scalar()
    return float(total or 0.0)
