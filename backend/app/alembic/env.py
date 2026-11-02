import os
import re
from datetime import datetime
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, make_url, pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# target_metadata = None

from app.models import SQLModel  # noqa
from app.core.config import settings  # noqa

target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    # Allow override via environment variable (used in tests)
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url
    return str(settings.SQLALCHEMY_DATABASE_URI)


_REV_ID_PATTERN = re.compile(r"^(?P<date>\d{8})_(?P<seq>\d{4})$")


def _get_versions_dir() -> Path:
    base_dir = Path(config.config_file_name).resolve().parent
    script_location = config.get_main_option("script_location")
    return (base_dir / script_location / "versions").resolve()


def _next_revision_id() -> str:
    date_prefix = datetime.now().strftime("%Y%m%d")
    max_seq = 0
    versions_dir = _get_versions_dir()
    if versions_dir.exists():
        for path in versions_dir.glob("*.py"):
            try:
                contents = path.read_text(encoding="utf-8")
            except OSError:
                continue
            match = re.search(
                r"^revision\s*=\s*['\"]([^'\"]+)['\"]",
                contents,
                re.MULTILINE,
            )
            if not match:
                continue
            rev_id = match.group(1)
            parsed = _REV_ID_PATTERN.match(rev_id)
            if not parsed or parsed.group("date") != date_prefix:
                continue
            seq = int(parsed.group("seq"))
            if seq > max_seq:
                max_seq = seq
    return f"{date_prefix}_{max_seq + 1:04d}"


def process_revision_directives(context, revision, directives):
    if getattr(config.cmd_opts, "rev_id", None):
        return
    if directives:
        directives[0].rev_id = _next_revision_id()


def _should_run_online_migrations() -> bool:
    cmd_opts = getattr(config, "cmd_opts", None)
    if cmd_opts is None:
        return True
    if getattr(cmd_opts, "cmd", None) == "revision" and not getattr(
        cmd_opts, "autogenerate", False
    ):
        return False
    return True


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    # replace postgresql+asyncpg with psycopg2 for Alembic compatibility
    # The URL carries the password, and this line ends up in container logs.
    shown = make_url(configuration["sqlalchemy.url"]).render_as_string(hide_password=True)
    print(f"Using database URL: {shown}")
    configuration["sqlalchemy.url"] = configuration["sqlalchemy.url"].replace("postgresql+asyncpg", "postgresql+psycopg")

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    if _should_run_online_migrations():
        run_migrations_online()
    else:
        run_migrations_offline()
