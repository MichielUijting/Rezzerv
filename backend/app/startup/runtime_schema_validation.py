"""Runtime schema validation only; Alembic exclusively owns schema mutation."""

from app.services.external_article_product_link_service import (
    ensure_external_article_product_link_schema,
)


def validate_runtime_schema(engine) -> None:
    with engine.begin() as connection:
        ensure_external_article_product_link_schema(connection)
