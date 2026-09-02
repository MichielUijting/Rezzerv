from app.services.postgresql_boolean_contract import (
    MIGRATED_BOOLEAN_COLUMNS_BY_TABLE,
    normalize_postgresql_boolean_parameters,
    normalize_postgresql_boolean_statement,
)


def test_explicit_migration_boolean_set_is_covered():
    assert MIGRATED_BOOLEAN_COLUMNS_BY_TABLE == {
        "household_permission_policies": frozenset({"member_allowed"}),
        "product_identities": frozenset({"is_primary"}),
        "purchase_import_lines": frozenset({"is_auto_prefilled"}),
        "receipt_sources": frozenset({"is_active"}),
        "receipt_table_lines": frozenset({"is_deleted", "is_validated"}),
        "receipt_tables": frozenset({"totals_overridden"}),
        "spaces": frozenset({"active"}),
        "sublocations": frozenset({"active"}),
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


def test_boolean_comparisons_are_scoped_to_migrated_table_column_pairs():
    sql = """
        SELECT * FROM product_identities
        WHERE is_primary = 0
          AND unrelated_counter = 0
          AND active = 1
    """
    normalized = normalize_postgresql_boolean_statement(sql)
    assert "is_primary = FALSE" in normalized
    assert "unrelated_counter = 0" in normalized
    assert "active = 1" in normalized

    spaces_sql = "SELECT * FROM spaces WHERE active = 1"
    assert "active = TRUE" in normalize_postgresql_boolean_statement(spaces_sql)


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


def test_receipt_approve_boolean_parameter_comparison_is_postgresql_native():
    sql = """
        UPDATE receipt_tables
        SET totals_overridden = %(totals_overridden)s,
            totals_override_by_user_email = CASE
                WHEN %(totals_overridden)s = 1 THEN %(user_email)s
                ELSE NULL
            END,
            totals_override_at = CASE
                WHEN %(totals_overridden)s = 1 THEN CURRENT_TIMESTAMP
                ELSE NULL
            END
        WHERE id = %(id)s
    """
    normalized = normalize_postgresql_boolean_statement(sql)
    assert "%(totals_overridden)s = 1" not in normalized
    assert "WHEN %(totals_overridden)s THEN" in normalized


def test_purchase_import_boolean_parameter_comparisons_are_postgresql_native():
    sql = """
        UPDATE purchase_import_lines
        SET is_auto_prefilled = CASE
                WHEN %(can_auto_fill)s = 1 THEN 1 ELSE 0
            END,
            matched_household_article_id = CASE
                WHEN %(can_auto_fill)s = 1 THEN %(matched_household_article_id)s
                ELSE NULL
            END,
            review_decision = CASE
                WHEN %(can_auto_fill)s = 1 THEN 'selected'
                ELSE 'pending'
            END
        WHERE id = %(id)s
    """
    normalized = normalize_postgresql_boolean_statement(sql)
    assert "%(can_auto_fill)s = 1" not in normalized
    assert "matched_household_article_id = CASE" in normalized
    assert "WHEN %(can_auto_fill)s THEN" in normalized


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


def test_non_migrated_table_values_are_not_globally_coerced():
    _, params = normalize_postgresql_boolean_parameters(
        "UPDATE unrelated_table SET value = :value WHERE id = :id",
        (),
        {"value": 1, "id": "row-1"},
    )
    assert params == {"value": 1, "id": "row-1"}
