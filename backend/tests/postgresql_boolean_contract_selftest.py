from app.services.postgresql_boolean_contract import (
    MIGRATED_BOOLEAN_COLUMNS,
    normalize_postgresql_boolean_parameters,
    normalize_postgresql_boolean_statement,
)


def test_explicit_migration_boolean_set_is_covered():
    assert MIGRATED_BOOLEAN_COLUMNS == {
        "member_allowed",
        "is_primary",
        "is_auto_prefilled",
        "is_active",
        "is_deleted",
        "is_validated",
        "totals_overridden",
        "active",
    }


def test_receipt_detail_boolean_coalesce_is_postgresql_native():
    sql = """
        SELECT COALESCE(is_deleted, 0) AS is_deleted,
               COALESCE(is_validated, 0) AS is_validated
        FROM receipt_table_lines
        WHERE receipt_table_id = %(receipt_table_id)s
    """
    normalized = normalize_postgresql_boolean_statement(sql)
    assert "COALESCE(is_deleted, FALSE)" in normalized
    assert "COALESCE(is_validated, FALSE)" in normalized
    assert "COALESCE(is_deleted, 0)" not in normalized
    assert "COALESCE(is_validated, 0)" not in normalized


def test_boolean_comparisons_are_native_for_migrated_columns_only():
    sql = """
        SELECT * FROM product_identities
        WHERE is_primary = 0
          AND unrelated_counter = 0
          AND active = 1
    """
    normalized = normalize_postgresql_boolean_statement(sql)
    assert "is_primary = FALSE" in normalized
    assert "active = TRUE" in normalized
    assert "unrelated_counter = 0" in normalized


def test_receipt_line_insert_literal_boolean_is_normalized():
    sql = """
        INSERT INTO receipt_table_lines
            (id, receipt_table_id, raw_label, is_deleted, is_validated)
        VALUES
            (%(id)s, %(receipt_table_id)s, %(raw_label)s, 0, 1)
        RETURNING id
    """
    normalized = normalize_postgresql_boolean_statement(sql)
    assert "FALSE" in normalized
    assert "TRUE" in normalized


def test_purchase_import_case_assignment_is_reduced_to_bool_parameter():
    sql = """
        UPDATE purchase_import_lines
        SET is_auto_prefilled = CASE
            WHEN %(can_auto_fill)s = 1 THEN 1
            ELSE 0
        END
        WHERE id = %(id)s
    """
    normalized = normalize_postgresql_boolean_statement(sql)
    assert "CASE" not in normalized.upper()
    assert "is_auto_prefilled = %(can_auto_fill)s" in normalized


def test_boolean_write_parameters_are_python_bools():
    _, params = normalize_postgresql_boolean_parameters(
        "UPDATE receipt_table_lines SET is_validated = :validated WHERE id = :id",
        (),
        {"validated": 1, "id": "line-1"},
    )
    assert params == {"validated": True, "id": "line-1"}

    _, params = normalize_postgresql_boolean_parameters(
        "UPDATE household_permission_policies SET member_allowed = :value WHERE id = :id",
        (),
        {"value": 0, "id": "policy-1"},
    )
    assert params == {"value": False, "id": "policy-1"}


def test_non_postgresql_boolean_like_values_are_not_globally_coerced():
    _, params = normalize_postgresql_boolean_parameters(
        "UPDATE unrelated_table SET value = :value WHERE id = :id",
        (),
        {"value": 1, "id": "row-1"},
    )
    assert params == {"value": 1, "id": "row-1"}
