from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = BACKEND_ROOT / "app" / "api" / "catalog_routes.py"
OFF_LINK_PATH = BACKEND_ROOT / "app" / "services" / "off_product_link_service.py"
OFF_SEARCH_PATH = BACKEND_ROOT / "app" / "services" / "off_search_service.py"
ARTICLE_UI_PATH = BACKEND_ROOT / "app" / "services" / "external_article_ui_projection.py"
ARTICLE_LINK_PATH = BACKEND_ROOT / "app" / "services" / "external_article_product_link_service.py"
CANDIDATE_STORE_PATH = BACKEND_ROOT / "app" / "services" / "external_product_candidate_store.py"
IDENTITY_POLICY_PATH = BACKEND_ROOT / "app" / "services" / "external_product_identity_policy.py"

# Houd deze scope gelijk aan de volledige OFF/GPC-gebruikersroute in de CI-workflow.
FORBIDDEN_SQL_PATTERNS = {
    "runtime CREATE TABLE": re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    "runtime CREATE INDEX": re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    "runtime ALTER TABLE": re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    "runtime DROP schema object": re.compile(
        r"\bDROP\s+(?:TABLE|INDEX|TRIGGER)\b", re.IGNORECASE
    ),
}


def _string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
    return None


def _text_sql_literals(source: str) -> list[str]:
    tree = ast.parse(source)
    sql: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        is_text = (
            isinstance(func, ast.Name) and func.id == "text"
        ) or (
            isinstance(func, ast.Attribute) and func.attr == "text"
        )
        if not is_text:
            continue
        value = _string_value(node.args[0])
        if value is not None:
            sql.append(value)
    return sql


def _assert_no_runtime_ddl() -> None:
    failures: list[str] = []
    for path in (CATALOG_PATH, OFF_LINK_PATH, OFF_SEARCH_PATH, ARTICLE_UI_PATH, ARTICLE_LINK_PATH, CANDIDATE_STORE_PATH):
        source = path.read_text(encoding="utf-8-sig")
        for index, sql in enumerate(_text_sql_literals(source), start=1):
            for label, pattern in FORBIDDEN_SQL_PATTERNS.items():
                if pattern.search(sql):
                    failures.append(f"{path.name}: SQL#{index}: {label}")
    if failures:
        raise AssertionError(
            "Catalog/OFF request paths contain runtime schema DDL:\n- "
            + "\n- ".join(sorted(failures))
        )
    print("POSTGRESQL_CATALOG_OFF_RUNTIME_DDL_ABSENT_GREEN")


def _assert_catalog_sql_portable() -> None:
    source = CATALOG_PATH.read_text(encoding="utf-8-sig")
    forbidden = {
        "SQLite COLLATE NOCASE": "COLLATE NOCASE",
        "SQLite datetime() receipt ordering": "datetime(pib.created_at)",
        "integer Boolean COALESCE": "COALESCE(is_primary, 0)",
    }
    present = [label for label, token in forbidden.items() if token in source]
    if present:
        raise AssertionError(f"Catalog SQL still contains non-portable constructs: {present}")

    required = (
        'sort_by in {"name", "catalog_kind", "brand", "primary_gtin", "product_type", "source"}',
        "LOWER({order_expression})",
        "COALESCE(is_primary, FALSE)",
        "ORDER BY pib.created_at DESC, pil.id DESC",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"Catalog PostgreSQL portability contract incomplete: {missing}")

    print("POSTGRESQL_CATALOG_CASE_INSENSITIVE_SORT_GREEN")
    print("POSTGRESQL_CATALOG_IDENTITY_BOOLEAN_READ_GREEN")
    print("POSTGRESQL_CATALOG_RECEIPT_TIMESTAMP_ORDER_GREEN")


def _assert_off_search_sql_portable() -> None:
    source = OFF_SEARCH_PATH.read_text(encoding="utf-8-sig")
    forbidden = (
        "COALESCE(rtl.quantity, '')",
        "COALESCE(rl.parsed_quantity, '')",
    )
    present = [token for token in forbidden if token in source]
    if present:
        raise AssertionError(
            f"OFF receipt resolution still mixes numeric values with empty text: {present}"
        )

    required = (
        "COALESCE(CAST(rtl.quantity AS TEXT), '')",
        "COALESCE(CAST(rl.parsed_quantity AS TEXT), '')",
        '"gpc_brick_code": gpc_brick_code',
        '"explicit_gpc_brick_code": gpc_brick_code',
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"OFF search portability/GPC contract incomplete: {missing}")

    print("POSTGRESQL_OFF_RECEIPT_NUMERIC_CAST_STATIC_GREEN")
    print("POSTGRESQL_OFF_GPC_PROPAGATION_STATIC_GREEN")


def _assert_external_article_ui_sql_portable() -> None:
    source = ARTICLE_UI_PATH.read_text(encoding="utf-8-sig")
    if "COALESCE(pgm.active, TRUE)" in source:
        raise AssertionError(
            "External article UI projection still treats integer membership active as BOOLEAN"
        )
    if "COALESCE(pgm.active, 1) = 1" not in source:
        raise AssertionError("External article UI membership predicate contract missing")

    print("POSTGRESQL_EXTERNAL_ARTICLE_UI_INTEGER_ACTIVE_STATIC_GREEN")


def _assert_off_identity_boolean_bind() -> None:
    source = OFF_LINK_PATH.read_text(encoding="utf-8-sig")
    forbidden = (
        "is_primary = 1",
        "1.0, 1, CURRENT_TIMESTAMP",
    )
    present = [token for token in forbidden if token in source]
    if present:
        raise AssertionError(f"OFF identity DML still uses integer Boolean literals: {present}")

    required = (
        "is_primary = :is_primary",
        "1.0, :is_primary, CURRENT_TIMESTAMP",
        '"is_primary": True',
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"OFF identity Boolean bind contract incomplete: {missing}")

    print("POSTGRESQL_OFF_IDENTITY_BOOLEAN_BIND_GREEN")


def _assert_global_external_link_authority() -> None:
    off_source = OFF_LINK_PATH.read_text(encoding="utf-8-sig")
    forbidden_household_writes = (
        "UPDATE household_articles",
        "UPDATE purchase_import_lines",
        "UPDATE receipt_table_lines",
        "UPDATE receipt_lines",
    )
    present = [token for token in forbidden_household_writes if token in off_source]
    if present:
        raise AssertionError(
            f"Platformbrede OFF-koppeling muteert nog huishoud-/bondata: {present}"
        )
    required_off = (
        "def _receipt_item_reference",
        "receipt_link = _receipt_item_reference(conn, receipt_item_id)",
        "confirm_external_article_for_receipt_item",
    )
    missing_off = [token for token in required_off if token not in off_source]
    if missing_off:
        raise AssertionError(f"Globale OFF-linkauthority ontbreekt: {missing_off}")

    candidate_source = CANDIDATE_STORE_PATH.read_text(encoding="utf-8-sig")
    if 'f"COALESCE({global_product_expr}, ha.global_product_id)"' in candidate_source:
        raise AssertionError(
            "Externe-databaseslisting gebruikt household_articles.global_product_id nog als globale fallback"
        )
    required_candidate = (
        '"source_global_product_id": source_global_product_id or None',
        '"global_product_id": None',
        '"status": "no_candidate"',
    )
    missing_candidate = [
        token for token in required_candidate if token not in candidate_source
    ]
    if missing_candidate:
        raise AssertionError(
            f"Globale receipt-projectiecontract ontbreekt: {missing_candidate}"
        )

    print("POSTGRESQL_OFF_GLOBAL_LINK_HOUSEHOLD_WRITE_ABSENT_GREEN")
    print("POSTGRESQL_EXTERNAL_RECEIPT_GLOBAL_AUTHORITY_STATIC_GREEN")


def _assert_private_label_identity_guard_wired() -> None:
    policy_source = IDENTITY_POLICY_PATH.read_text(encoding="utf-8-sig")
    off_source = OFF_LINK_PATH.read_text(encoding="utf-8-sig")
    search_source = OFF_SEARCH_PATH.read_text(encoding="utf-8-sig")
    ui_source = ARTICLE_UI_PATH.read_text(encoding="utf-8-sig")

    required_policy = (
        "def external_product_identity_compatibility",
        "def assert_external_product_identity_compatible",
        "private_label_brand_conflict",
    )
    missing_policy = [token for token in required_policy if token not in policy_source]
    if missing_policy:
        raise AssertionError(
            f"Private-label identity policy incompleet: {missing_policy}"
        )

    if "assert_external_product_identity_compatible(" not in off_source:
        raise AssertionError("OFF write-route mist private-label identity guard")
    if "external_product_identity_compatibility(" not in search_source:
        raise AssertionError("OFF zoekroute mist private-label kandidaatfilter")
    if 'add("private_label_phrase", source_receipt_text, 1.2)' not in search_source:
        raise AssertionError("OFF zoekroute mist expliciete huismerk-queryvariant")
    if "external_product_identity_compatibility(" not in ui_source:
        raise AssertionError("Externe-databasesprojectie mist stale-link identity guard")
    if '"central_link_identity_rejected"' not in ui_source:
        raise AssertionError("Externe-databasesprojectie rapporteert identity rejection niet")

    print("POSTGRESQL_OFF_PRIVATE_LABEL_IDENTITY_STATIC_GREEN")


def _assert_generic_catalog_link_contract() -> None:
    off_source = OFF_LINK_PATH.read_text(encoding="utf-8-sig")
    search_source = OFF_SEARCH_PATH.read_text(encoding="utf-8-sig")
    ui_source = ARTICLE_UI_PATH.read_text(encoding="utf-8-sig")
    link_source = ARTICLE_LINK_PATH.read_text(encoding="utf-8-sig")

    required_off = (
        "def link_generic_product_with_product_type",
        "gtin=None",
        'source="external_databases_generic"',
        'confirmed_by="external_databases_generic_link"',
    )
    missing_off = [token for token in required_off if token not in off_source]
    if missing_off:
        raise AssertionError(f"Generieke Cataloguskoppeling incompleet: {missing_off}")

    required_link = (
        'is_generic_catalog_product = product_source == "external_databases_generic"',
        '"link_mode": "generic" if is_generic_catalog_product else "exact"',
        '"is_generic_catalog_product": is_generic_catalog_product',
    )
    missing_link = [token for token in required_link if token not in link_source]
    if missing_link:
        raise AssertionError(
            f"Centraal exact/generiek completeness-contract incompleet: {missing_link}"
        )

    required_ui = (
        'confirmed_by")) == "external_databases_generic_link"',
        '"central_link_mode"',
        '"is_generic_catalog_link"',
    )
    missing_ui = [token for token in required_ui if token not in ui_source]
    if missing_ui:
        raise AssertionError(f"Generieke projectie incompleet: {missing_ui}")

    manual_start = search_source.find('    if mode == "manual":')
    manual_end = search_source.find(
        "    else:\n        query, provider, results, query_diagnostics = _automatic_search",
        manual_start,
    )
    if manual_start < 0 or manual_end < 0:
        raise AssertionError("Handmatige OFF-zoekroute kon niet worden afgebakend")
    manual_source = search_source[manual_start:manual_end]
    if 'result["identity_compatible"] = bool(identity_check.get("ok"))' not in manual_source:
        raise AssertionError("Handmatige OFF-resultaten missen identiteitswaarschuwing")
    if 'if not identity_check.get("ok"):\n                continue' in manual_source:
        raise AssertionError(
            "Handmatige OFF-zoekroute filtert conflicterende merken nog volledig weg"
        )

    print("POSTGRESQL_GENERIC_CATALOG_LINK_STATIC_GREEN")
    print("POSTGRESQL_OFF_MANUAL_SEARCH_BROAD_STATIC_GREEN")


def main() -> None:
    for path in (
        CATALOG_PATH,
        OFF_LINK_PATH,
        OFF_SEARCH_PATH,
        ARTICLE_UI_PATH,
        ARTICLE_LINK_PATH,
        CANDIDATE_STORE_PATH,
        IDENTITY_POLICY_PATH,
    ):
        if not path.is_file():
            raise AssertionError(f"Catalog/OFF scope file ontbreekt: {path}")
    _assert_no_runtime_ddl()
    _assert_catalog_sql_portable()
    _assert_off_search_sql_portable()
    _assert_external_article_ui_sql_portable()
    _assert_off_identity_boolean_bind()
    _assert_global_external_link_authority()
    _assert_private_label_identity_guard_wired()
    _assert_generic_catalog_link_contract()
    print("POSTGRESQL_CATALOG_OFF_REQUEST_PORTABILITY_STATIC_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
