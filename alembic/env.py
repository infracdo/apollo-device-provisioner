from logging.config import fileConfig
import os
import sys
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import the Base and models
from app.database import Base
from app.models import Device, ONU, Queue  # Import all models to register them with Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    """Get database URL from environment or config file"""
    # Try to get ALEMBIC_DATABASE_URL first (sync URL for migrations)
    url = os.getenv("ALEMBIC_DATABASE_URL")
    
    if not url:
        # Fall back to DATABASE_URL and convert asyncpg to psycopg2
        url = os.getenv("DATABASE_URL")
        if url and "asyncpg" in url:
            url = url.replace("+asyncpg", "+psycopg2")
    
    if not url:
        # Try to load from .env file
        try:
            from dotenv import load_dotenv
            load_dotenv()
            url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
            if url and "asyncpg" in url:
                url = url.replace("+asyncpg", "+psycopg2")
        except ImportError:
            pass
    
    if not url:
        # Fall back to config file
        url = config.get_main_option("sqlalchemy.url")
    
    if not url:
        raise ValueError(
            "No database URL found. Set DATABASE_URL or ALEMBIC_DATABASE_URL environment variable "
            "or configure sqlalchemy.url in alembic.ini"
        )
    
    # Convert postgres:// to postgresql:// for SQLAlchemy compatibility
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    return url


def run_migrations_offline() -> None:
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
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
