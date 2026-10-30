"""Alembic environment. Migrations run as the schema-owner role only."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

from customerpulse.database.models import Base
from customerpulse.database.roles import SCHEMA
from customerpulse.settings import get_settings, normalise_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # Alembic's own version table lives in the same schema; never diff it.
    return not (type_ == "table" and name == "alembic_version")


def _url() -> str:
    url = get_settings().migrator_database_url
    if not url:
        raise RuntimeError("MIGRATOR_DATABASE_URL is not configured")
    return normalise_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=SCHEMA,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.execute(f"SET search_path TO {SCHEMA}")
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        connection.execute(text(f"SET search_path TO {SCHEMA}"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=SCHEMA,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
