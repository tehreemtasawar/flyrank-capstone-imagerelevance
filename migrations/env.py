from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  (register tables)
from app.config import settings
from app.database import Base

config = context.config
target_metadata = Base.metadata


def _url():
    # run_migrations() sets this explicitly; CLI use falls back to DATABASE_URL
    return config.get_main_option("sqlalchemy.url") or settings.DATABASE_URL


def run_migrations_online():
    connect_args = {"check_same_thread": False} if _url().startswith("sqlite") else {}
    engine = create_engine(_url().replace("%%", "%"), poolclass=pool.NullPool, connect_args=connect_args)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
