from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")


def test_receipt_auto_approval_is_household_setting_and_admin_guarded():
    assert 'RECEIPT_AUTO_APPROVE_KEY = "receipt_auto_approve"' in SOURCE
    assert 'receipt_auto_approve: bool = RECEIPT_AUTO_APPROVE_DEFAULT' in SOURCE
    assert 'context = require_household_admin_context(authorization)' in SOURCE
    assert '"can_edit_receipt_auto_approve": can_edit' in SOURCE


def test_receipt_auto_approval_reuses_manual_authority_and_fails_closed():
    assert "def _approve_receipt_table_in_transaction(" in SOURCE
    assert "allow_totals_override=False" in SOURCE
    assert "Totaalbedrag wijkt af; automatische goedkeuring is gestopt" in SOURCE
    assert "purchase_date_requires_review" in SOURCE
    assert "store_requires_review" in SOURCE
    assert "_auto_approve_pending_receipts_for_household(effective_household_id)" in SOURCE
