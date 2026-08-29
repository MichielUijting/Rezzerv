"""Move external catalog request-path schema and bootstrap authority to Alembic.

Revision ID: 20260829_07
Revises: 20260829_06
Create Date: 2026-08-29
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_07"
down_revision: Union[str, None] = "20260829_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CANDIDATES = "external_product_candidates"
_CANDIDATE_INDEX = "idx_external_product_candidates_context"
_EXTERNAL_INDEX = "external_product_index"
_EXTERNAL_INDEX_INDEXES: dict[str, tuple[str, ...]] = {
    "idx_external_product_index_gtin": ("gtin",),
    "idx_external_product_index_source": ("source_name",),
    "idx_external_product_index_search": ("normalized_search_text",),
}
_BATCH_DECISIONS = "external_relation_batch_decisions"
_BATCH_INDEX = "idx_external_relation_batch_decisions_candidate"

_DATA_ROOT = Path(__file__).resolve().parents[2] / "app" / "data"
_TAXONOMY_SEED_PATH = _DATA_ROOT / "product_taxonomy_seed.json"
_LIDL_CATALOG_SEED_PATH = _DATA_ROOT / "lidl_catalog_enrichment_seed.json"
_TAXONOMY_INDEX_RETAILERS: tuple[tuple[str, str], ...] = (
    ("lidl", "Lidl"),
    ("jumbo", "Jumbo"),
    ("albert heijn", "Albert Heijn"),
    ("aldi", "Aldi"),
    ("plus", "PLUS"),
)

_CANDIDATE_TEXT_COLUMNS = (
    "receipt_line_id",
    "purchase_import_line_id",
    "context_key",
    "retailer_code",
    "receipt_line_text",
    "candidate_name",
    "candidate_brand",
    "candidate_category",
    "candidate_source_name",
    "candidate_source_product_code",
    "candidate_source_url",
    "source_name",
    "source_product_code",
    "retailer_article_number",
    "external_article_code",
    "quantity_label",
    "variant",
    "source_url",
    "score_breakdown_json",
    "raw_payload",
    "global_product_id",
    "status",
    "candidate_status",
    "created_by",
    "created_at",
    "updated_at",
)
_CANDIDATE_BOOL_COLUMNS = (
    "is_probable",
    "is_user_confirmed",
    "is_external_database_override",
)
_EXTERNAL_INDEX_TEXT_COLUMNS = (
    "source_name",
    "source_product_code",
    "gtin",
    "ean",
    "code",
    "product_name",
    "brand",
    "brands",
    "quantity",
    "net_content",
    "packaging",
    "category",
    "categories",
    "image_url",
    "source_url",
    "retailer_code",
    "normalized_search_text",
    "created_at",
    "updated_at",
)
_BATCH_TEXT_COLUMNS = (
    "candidate_id",
    "household_article_id",
    "global_product_id",
    "decision",
    "decision_reason",
    "created_by",
    "created_at",
    "updated_at",
)


def _inspector(bind: sa.engine.Connection) -> sa.Inspector:
    return sa.inspect(bind)


def _columns(bind: sa.engine.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    return {
        str(column.get("name") or ""): column
        for column in _inspector(bind).get_columns(table_name)
    }


def _index_map(bind: sa.engine.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    return {
        str(index.get("name") or ""): index
        for index in _inspector(bind).get_indexes(table_name)
    }


def _boolean_column(bind: sa.engine.Connection, name: str) -> sa.Column[Any]:
    if bind.dialect.name == "postgresql":
        return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("false"))
    return sa.Column(name, sa.Integer(), nullable=False, server_default=sa.text("0"))


def _ensure_candidates(bind: sa.engine.Connection) -> None:
    inspector = _inspector(bind)
    if not inspector.has_table(_CANDIDATES):
        op.create_table(
            _CANDIDATES,
            sa.Column("id", sa.Text(), primary_key=True),
            *[sa.Column(name, sa.Text()) for name in _CANDIDATE_TEXT_COLUMNS],
            sa.Column("score", sa.Float()),
            *[_boolean_column(bind, name) for name in _CANDIDATE_BOOL_COLUMNS],
        )
    else:
        columns = _columns(bind, _CANDIDATES)
        if "id" not in columns:
            raise RuntimeError(f"{_CANDIDATES} mist primaire identiteit id")
        for name in _CANDIDATE_TEXT_COLUMNS:
            if name not in columns:
                op.add_column(_CANDIDATES, sa.Column(name, sa.Text()))
        if "score" not in columns:
            op.add_column(_CANDIDATES, sa.Column("score", sa.Float()))
        for name in _CANDIDATE_BOOL_COLUMNS:
            if name not in columns:
                op.add_column(_CANDIDATES, _boolean_column(bind, name))

    indexes = _index_map(bind, _CANDIDATES)
    existing = indexes.get(_CANDIDATE_INDEX)
    expected = (
        "context_key",
        "retailer_code",
        "candidate_source_name",
        "candidate_source_product_code",
        "variant",
    )
    if existing is None:
        op.create_index(_CANDIDATE_INDEX, _CANDIDATES, list(expected), unique=False)
    elif tuple(existing.get("column_names") or ()) != expected or bool(existing.get("unique")):
        raise RuntimeError(f"{_CANDIDATE_INDEX} wijkt af van het canonical external-candidate contract")


def _ensure_external_index(bind: sa.engine.Connection) -> None:
    inspector = _inspector(bind)
    if not inspector.has_table(_EXTERNAL_INDEX):
        op.create_table(
            _EXTERNAL_INDEX,
            sa.Column("id", sa.Text(), primary_key=True),
            *[sa.Column(name, sa.Text()) for name in _EXTERNAL_INDEX_TEXT_COLUMNS],
        )
    else:
        columns = _columns(bind, _EXTERNAL_INDEX)
        if "id" not in columns:
            raise RuntimeError(f"{_EXTERNAL_INDEX} mist primaire identiteit id")
        for name in _EXTERNAL_INDEX_TEXT_COLUMNS:
            if name not in columns:
                op.add_column(_EXTERNAL_INDEX, sa.Column(name, sa.Text()))

    indexes = _index_map(bind, _EXTERNAL_INDEX)
    for index_name, expected_columns in _EXTERNAL_INDEX_INDEXES.items():
        existing = indexes.get(index_name)
        if existing is None:
            op.create_index(index_name, _EXTERNAL_INDEX, list(expected_columns), unique=False)
            indexes = _index_map(bind, _EXTERNAL_INDEX)
            continue
        if tuple(existing.get("column_names") or ()) != expected_columns or bool(existing.get("unique")):
            raise RuntimeError(f"{index_name} wijkt af van het canonical external-index contract")


def _ensure_batch_decisions(bind: sa.engine.Connection) -> None:
    inspector = _inspector(bind)
    if not inspector.has_table(_BATCH_DECISIONS):
        op.create_table(
            _BATCH_DECISIONS,
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("candidate_id", sa.Text(), nullable=False),
            sa.Column("household_article_id", sa.Text()),
            sa.Column("global_product_id", sa.Text()),
            sa.Column("decision", sa.Text(), nullable=False),
            sa.Column("decision_reason", sa.Text()),
            sa.Column("created_by", sa.Text()),
            sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.Text()),
        )
    else:
        columns = _columns(bind, _BATCH_DECISIONS)
        required_identity = {"id", "candidate_id", "decision"}
        missing_identity = required_identity - set(columns)
        if missing_identity:
            raise RuntimeError(
                f"{_BATCH_DECISIONS} mist canonical identitykolommen: {sorted(missing_identity)}"
            )
        for name in _BATCH_TEXT_COLUMNS:
            if name not in columns:
                op.add_column(_BATCH_DECISIONS, sa.Column(name, sa.Text()))

    indexes = _index_map(bind, _BATCH_DECISIONS)
    expected = ("candidate_id", "household_article_id", "decision")
    existing = indexes.get(_BATCH_INDEX)
    if existing is None:
        op.create_index(_BATCH_INDEX, _BATCH_DECISIONS, list(expected), unique=False)
    elif tuple(existing.get("column_names") or ()) != expected or bool(existing.get("unique")):
        raise RuntimeError(f"{_BATCH_INDEX} wijkt af van het canonical relation-batch contract")


def _normalize_index_text(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace(".", " ").replace("-", " ")
    normalized = re.sub(
        r"[^a-z0-9áéíóúàèìòùäëïöüâêîôûçñ\s]+",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    return " ".join(normalized.split())


def _load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Canonical external-catalog seed ontbreekt: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Canonical external-catalog seed is ongeldig: {path}")
    return payload or fallback


def _external_index_seed_rows() -> list[dict[str, Any]]:
    taxonomy_payload = _load_json(_TAXONOMY_SEED_PATH, {"taxonomy": []})
    catalog_payload = _load_json(_LIDL_CATALOG_SEED_PATH, {"rules": []})
    timestamp = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []

    for retailer_code, retailer_name in _TAXONOMY_INDEX_RETAILERS:
        for item in taxonomy_payload.get("taxonomy") or []:
            if not isinstance(item, dict):
                continue
            intent_key = str(item.get("intent_key") or "").strip()
            if not intent_key:
                continue
            canonical = str(item.get("canonical_name") or intent_key).strip()
            category = str(item.get("category") or "").strip()
            product_type = str(item.get("product_type") or "").strip()
            synonyms = [str(value or "") for value in (item.get("synonyms") or [])]
            source_product_code = f"{retailer_code}:{intent_key}"
            product_name = f"{retailer_name} {canonical}".strip()
            brand = retailer_name
            rows.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"rezzerv-taxonomy-index:{retailer_code}:{intent_key}")),
                "source_name": "product_taxonomy_seed",
                "source_product_code": source_product_code,
                "gtin": "",
                "ean": "",
                "code": source_product_code,
                "product_name": product_name,
                "brand": brand,
                "brands": brand,
                "quantity": "",
                "net_content": "",
                "packaging": "",
                "category": category,
                "categories": category,
                "image_url": "",
                "source_url": "",
                "retailer_code": retailer_code,
                "normalized_search_text": _normalize_index_text(" ".join([
                    retailer_name,
                    retailer_code,
                    brand,
                    product_name,
                    canonical,
                    category,
                    product_type,
                    intent_key,
                    *synonyms,
                    source_product_code,
                ])),
                "created_at": timestamp,
                "updated_at": timestamp,
            })

    for rule in catalog_payload.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        source_product_code = str(rule.get("source_product_code") or "").strip()
        if not source_product_code:
            continue
        product_name = str(rule.get("catalog_product_name") or "").strip()
        brand = str(rule.get("brand") or "").strip()
        category = str(rule.get("category") or "").strip()
        quantity = str(rule.get("quantity_label") or "").strip()
        search_terms = [str(value or "") for value in (rule.get("search_terms") or [])]
        rows.append({
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"rezzerv-catalog-index:lidl:{source_product_code}")),
            "source_name": "lidl_catalog_enrichment",
            "source_product_code": source_product_code,
            "gtin": "",
            "ean": "",
            "code": source_product_code,
            "product_name": product_name,
            "brand": brand,
            "brands": brand,
            "quantity": quantity,
            "net_content": quantity,
            "packaging": quantity,
            "category": category,
            "categories": category,
            "image_url": "",
            "source_url": str(rule.get("source_url") or "").strip(),
            "retailer_code": "lidl",
            "normalized_search_text": _normalize_index_text(" ".join([
                "lidl",
                brand,
                product_name,
                category,
                quantity,
                source_product_code,
                *search_terms,
            ])),
            "created_at": timestamp,
            "updated_at": timestamp,
        })
    if not rows:
        raise RuntimeError("Canonical external_product_index seed is leeg")
    return rows


def _seed_external_index(bind: sa.engine.Connection) -> None:
    for row in _external_index_seed_rows():
        exists = bind.execute(
            sa.text(f"SELECT 1 FROM {_EXTERNAL_INDEX} WHERE id = :id"),
            {"id": row["id"]},
        ).first()
        if exists:
            bind.execute(
                sa.text(
                    f"""
                    UPDATE {_EXTERNAL_INDEX}
                    SET source_name = :source_name,
                        source_product_code = :source_product_code,
                        gtin = :gtin,
                        ean = :ean,
                        code = :code,
                        product_name = :product_name,
                        brand = :brand,
                        brands = :brands,
                        quantity = :quantity,
                        net_content = :net_content,
                        packaging = :packaging,
                        category = :category,
                        categories = :categories,
                        image_url = :image_url,
                        source_url = :source_url,
                        retailer_code = :retailer_code,
                        normalized_search_text = :normalized_search_text,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                row,
            )
        else:
            bind.execute(
                sa.text(
                    f"""
                    INSERT INTO {_EXTERNAL_INDEX} (
                        id, source_name, source_product_code, gtin, ean, code,
                        product_name, brand, brands, quantity, net_content, packaging,
                        category, categories, image_url, source_url, retailer_code,
                        normalized_search_text, created_at, updated_at
                    ) VALUES (
                        :id, :source_name, :source_product_code, :gtin, :ean, :code,
                        :product_name, :brand, :brands, :quantity, :net_content, :packaging,
                        :category, :categories, :image_url, :source_url, :retailer_code,
                        :normalized_search_text, :created_at, :updated_at
                    )
                    """
                ),
                row,
            )


def _validate_boolean_columns(bind: sa.engine.Connection) -> None:
    columns = _columns(bind, _CANDIDATES)
    for name in _CANDIDATE_BOOL_COLUMNS:
        column_type = columns[name].get("type")
        if bind.dialect.name == "postgresql" and not isinstance(column_type, sa.Boolean):
            raise RuntimeError(f"{_CANDIDATES}.{name} moet PostgreSQL BOOLEAN zijn, kreeg {column_type!r}")
        if bind.dialect.name == "sqlite" and not isinstance(column_type, sa.Integer):
            raise RuntimeError(f"{_CANDIDATES}.{name} moet SQLite INTEGER/BOOLEAN zijn, kreeg {column_type!r}")


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = _inspector(bind)
    for table_name in (_CANDIDATES, _EXTERNAL_INDEX, _BATCH_DECISIONS):
        if not inspector.has_table(table_name):
            raise RuntimeError(f"Canonical external-catalog tabel ontbreekt: {table_name}")

    candidate_columns = set(_columns(bind, _CANDIDATES))
    expected_candidates = {
        "id",
        "score",
        *_CANDIDATE_TEXT_COLUMNS,
        *_CANDIDATE_BOOL_COLUMNS,
    }
    missing_candidates = expected_candidates - candidate_columns
    if missing_candidates:
        raise RuntimeError(f"{_CANDIDATES} mist canonical kolommen: {sorted(missing_candidates)}")

    index_columns = set(_columns(bind, _EXTERNAL_INDEX))
    expected_index = {"id", *_EXTERNAL_INDEX_TEXT_COLUMNS}
    missing_index = expected_index - index_columns
    if missing_index:
        raise RuntimeError(f"{_EXTERNAL_INDEX} mist canonical kolommen: {sorted(missing_index)}")

    batch_columns = set(_columns(bind, _BATCH_DECISIONS))
    expected_batch = {"id", *_BATCH_TEXT_COLUMNS}
    missing_batch = expected_batch - batch_columns
    if missing_batch:
        raise RuntimeError(f"{_BATCH_DECISIONS} mist canonical kolommen: {sorted(missing_batch)}")

    _validate_boolean_columns(bind)

    candidate_index = _index_map(bind, _CANDIDATES).get(_CANDIDATE_INDEX)
    if tuple((candidate_index or {}).get("column_names") or ()) != (
        "context_key",
        "retailer_code",
        "candidate_source_name",
        "candidate_source_product_code",
        "variant",
    ):
        raise RuntimeError(f"Canonical candidate index ontbreekt of wijkt af: {_CANDIDATE_INDEX}")

    for index_name, expected_columns in _EXTERNAL_INDEX_INDEXES.items():
        index = _index_map(bind, _EXTERNAL_INDEX).get(index_name)
        if tuple((index or {}).get("column_names") or ()) != expected_columns:
            raise RuntimeError(f"Canonical external index ontbreekt of wijkt af: {index_name}")

    batch_index = _index_map(bind, _BATCH_DECISIONS).get(_BATCH_INDEX)
    if tuple((batch_index or {}).get("column_names") or ()) != (
        "candidate_id",
        "household_article_id",
        "decision",
    ):
        raise RuntimeError(f"Canonical relation-batch index ontbreekt of wijkt af: {_BATCH_INDEX}")

    seed_count = int(bind.execute(sa.text(
        f"SELECT COUNT(*) FROM {_EXTERNAL_INDEX} "
        "WHERE source_name IN ('product_taxonomy_seed', 'lidl_catalog_enrichment')"
    )).scalar_one())
    if seed_count <= 0:
        raise RuntimeError("Canonical external_product_index bootstrapdata ontbreekt")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")
    _ensure_candidates(bind)
    _ensure_external_index(bind)
    _ensure_batch_decisions(bind)
    _seed_external_index(bind)
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The PR2h external-catalog request authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
