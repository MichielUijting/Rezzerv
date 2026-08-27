from __future__ import annotations

import importlib

from alembic import context

from app.db import Base, engine


_MODEL_MODULES = (
    "app.models.household",
    "app.models.inventory",
    "app.models.purchase_import",
    "app.models.receipt",
    "app.models.space",
    "app.models.store_connection",
    "app.models.store_provider",
    "app.models.sublocation",
)

for _module_name in _MODEL_MODULES:
    importlib.import_module(_module_name)

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
            transaction_per_migration=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
