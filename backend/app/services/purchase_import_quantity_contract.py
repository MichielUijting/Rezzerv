"""Runtime precision contract for purchase-import quantities."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator


MAX_PURCHASE_IMPORT_QUANTITY_DECIMAL_PLACES = 2


class PurchaseImportQuantityPrecisionError(ValueError):
    """Raised when quantity_raw carries meaningful precision beyond the product contract."""


def _as_decimal(value: Any, *, label: str) -> Decimal:
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise PurchaseImportQuantityPrecisionError(
            f"{label} is not a valid decimal quantity: {value!r}"
        ) from exc
    if not decimal_value.is_finite():
        raise PurchaseImportQuantityPrecisionError(
            f"{label} must be a finite decimal quantity: {value!r}"
        )
    return decimal_value


def has_meaningful_precision_beyond_two_decimals(value: Any) -> bool:
    """Return True only when a numeric value has meaningful digits beyond 2 decimals."""

    decimal_value = _as_decimal(value, label="purchase_import_lines.quantity_raw")
    return decimal_value.normalize().as_tuple().exponent < -MAX_PURCHASE_IMPORT_QUANTITY_DECIMAL_PLACES


def validate_purchase_import_quantity_raw(value: Any) -> Decimal | None:
    """Validate quantity_raw without rounding or otherwise changing a valid value."""

    if value is None:
        return None
    decimal_value = _as_decimal(value, label="purchase_import_lines.quantity_raw")
    if decimal_value.normalize().as_tuple().exponent < -MAX_PURCHASE_IMPORT_QUANTITY_DECIMAL_PLACES:
        raise PurchaseImportQuantityPrecisionError(
            "purchase_import_lines.quantity_raw supports at most 2 meaningful decimal places; "
            f"received {value!r}"
        )
    return decimal_value


def _parameter_sets(multiparams: Any, params: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(params, Mapping) and params:
        yield params
    for item in multiparams or ():
        if isinstance(item, Mapping):
            yield item


def enforce_purchase_import_quantity_precision_before_execute(
    conn: Any,
    clauseelement: Any,
    multiparams: Any,
    params: Any,
    execution_options: Any,
) -> None:
    """SQLAlchemy before_execute hook covering current runtime SQL write paths."""

    statement = str(clauseelement).lower()
    if "purchase_import_lines" not in statement or "quantity_raw" not in statement:
        return
    if "insert" not in statement and "update" not in statement:
        return

    for parameter_set in _parameter_sets(multiparams, params):
        if "quantity_raw" in parameter_set:
            validate_purchase_import_quantity_raw(parameter_set["quantity_raw"])
