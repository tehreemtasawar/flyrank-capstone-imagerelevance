import pytest
from sqlalchemy import create_engine, inspect

from app.embedding_service import cosine_similarity
from app.matching import rank_images


def test_migrations_create_all_tables_and_indexes():
    from app.database import engine
    insp = inspect(engine)
    assert {"images", "posts", "suggestions", "cost_log", "batch_jobs", "alembic_version"} <= set(insp.get_table_names())
    idx = {i["name"] for i in insp.get_indexes("suggestions")}
    assert {"ix_suggestions_post_id", "ix_suggestions_image_id", "ix_suggestions_post_image"} <= idx
    assert {"ix_images_subject", "ix_images_category"} <= {i["name"] for i in insp.get_indexes("images")}


def test_rank_images_sorts_desc_and_skips_unembedded():
    imgs = [{"image_id": 1, "embedding": [0, 1]}, {"image_id": 2, "embedding": [1, 0]}, {"image_id": 3, "embedding": None}]
    r = rank_images([1, 0], imgs)
    assert [i["image_id"] for i in r] == [2, 1] and r[0]["similarity_score"] == pytest.approx(1.0)


def test_cosine_dimension_mismatch_raises_instead_of_returning_garbage():
    with pytest.raises(ValueError):
        cosine_similarity([1, 0], [1, 0, 0])


def test_cosine_zero_vector_is_zero():
    assert cosine_similarity([0, 0], [1, 1]) == 0.0
