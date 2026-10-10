"""initial schema: images, posts, suggestions, cost_log, batch_jobs

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "images",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("filename", sa.String, nullable=False, unique=True),
        sa.Column("path", sa.String, nullable=False),
        sa.Column("subject", sa.String),
        sa.Column("category", sa.String),
        sa.Column("attributes_json", sa.Text),
        sa.Column("caption", sa.String),
        sa.Column("confidence", sa.Float),
        sa.Column("flagged_low_confidence", sa.Boolean),
        sa.Column("embedding_json", sa.Text),
        sa.Column("embedding_model", sa.String),
        sa.Column("vision_model", sa.String),
        sa.Column("processed", sa.Boolean),
        sa.Column("processing_error", sa.String),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_images_id", "images", ["id"])
    op.create_index("ix_images_subject", "images", ["subject"])
    op.create_index("ix_images_category", "images", ["category"])

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("embedding_json", sa.Text),
        sa.Column("embedding_model", sa.String),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_posts_id", "posts", ["id"])

    op.create_table(
        "suggestions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("post_id", sa.Integer, sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("image_id", sa.Integer, sa.ForeignKey("images.id")),
        sa.Column("similarity_score", sa.Float),
        sa.Column("guard_decision", sa.String, nullable=False),
        sa.Column("guard_reason", sa.String, nullable=False),
        sa.Column("review_status", sa.String),
        sa.Column("reviewed_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_suggestions_id", "suggestions", ["id"])
    op.create_index("ix_suggestions_post_id", "suggestions", ["post_id"])
    op.create_index("ix_suggestions_image_id", "suggestions", ["image_id"])
    op.create_index("ix_suggestions_review_status", "suggestions", ["review_status"])
    op.create_index("ix_suggestions_post_image", "suggestions", ["post_id", "image_id"])

    op.create_table(
        "cost_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("call_type", sa.String, nullable=False),
        sa.Column("ref_table", sa.String, nullable=False),
        sa.Column("ref_id", sa.Integer, nullable=False),
        sa.Column("model_name", sa.String, nullable=False),
        sa.Column("estimated_cost_usd", sa.Float),
        sa.Column("success", sa.Boolean),
        sa.Column("note", sa.String),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_cost_log_id", "cost_log", ["id"])
    op.create_index("ix_cost_log_created_at", "cost_log", ["created_at"])
    op.create_index("ix_cost_log_ref", "cost_log", ["ref_table", "ref_id"])

    op.create_table(
        "batch_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("total", sa.Integer),
        sa.Column("processed", sa.Integer),
        sa.Column("flagged_low_confidence", sa.Integer),
        sa.Column("failed", sa.Integer),
        sa.Column("skipped", sa.Integer),
        sa.Column("error", sa.String),
        sa.Column("created_at", sa.DateTime),
        sa.Column("started_at", sa.DateTime),
        sa.Column("finished_at", sa.DateTime),
    )
    op.create_index("ix_batch_jobs_id", "batch_jobs", ["id"])
    op.create_index("ix_batch_jobs_status", "batch_jobs", ["status"])


def downgrade():
    for t in ("batch_jobs", "cost_log", "suggestions", "posts", "images"):
        op.drop_table(t)
