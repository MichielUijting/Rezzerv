from decimal import Decimal

from sqlalchemy.dialects import postgresql

from app.models.purchase_import import PurchaseImportLine
from app.models.receipt import ReceiptTableLine


def test_quantity_columns_do_not_impose_generic_scale():
    quantity_columns = (
        PurchaseImportLine.__table__.c.quantity_raw,
        ReceiptTableLine.__table__.c.quantity,
    )

    for column in quantity_columns:
        assert column.type.precision is None
        assert column.type.scale is None
        assert column.type.compile(dialect=postgresql.dialect()) == "NUMERIC"


def test_quantity_models_preserve_arbitrary_decimal_scale():
    for value in (Decimal("0.404"), Decimal("1.224"), Decimal("1.234567")):
        purchase_line = PurchaseImportLine(quantity_raw=value)
        receipt_line = ReceiptTableLine(quantity=value)

        assert purchase_line.quantity_raw == value
        assert receipt_line.quantity == value


def test_financial_scales_are_not_relaxed_by_quantity_contract_change():
    assert PurchaseImportLine.__table__.c.line_price_raw.type.scale == 2
    assert ReceiptTableLine.__table__.c.line_total.type.scale == 2
    assert ReceiptTableLine.__table__.c.discount_amount.type.scale == 2
