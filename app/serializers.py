"""Model -> response-schema helpers shared by the routers."""
from app.models import Image, Suggestion
from app.schemas import ImageOut, SuggestionOut


def image_out(img: Image) -> ImageOut:
    return ImageOut(
        id=img.id, filename=img.filename, subject=img.subject, category=img.category,
        attributes=img.attributes(), caption=img.caption, confidence=img.confidence,
        flagged_low_confidence=bool(img.flagged_low_confidence), processed=bool(img.processed),
        processing_error=img.processing_error,
    )


def suggestion_out(s: Suggestion) -> SuggestionOut:
    return SuggestionOut(
        id=s.id, post_id=s.post_id, image_id=s.image_id, similarity_score=s.similarity_score,
        guard_decision=s.guard_decision, guard_reason=s.guard_reason, review_status=s.review_status,
        image=image_out(s.image) if s.image else None,
    )
