"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Contract voor de kassabon -> Uitpakken -> Voorraad-ketentest
- Runtime Type: test
- Status Authority: no
- Refactor Status: keep_test

Deze eerste stap legt uitsluitend het vaste testcontract vast.
Er wordt nog geen productiecode, runtime-database of bestaande regressietest gewijzigd.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


TEST_HOUSEHOLD_ID = "0"
TEST_SCENARIO_ID = "receipt-inventory-chain"
TEST_PRODUCT_NAME = "AH BANANEN"
TEST_LOCATION_NAME = "Keuken"
TEST_SUBLOCATION_NAME = "Fruitschaal"


@dataclass(frozen=True)
class ReceiptScenario:
    receipt_key: str
    quantity: Decimal


FIRST_RECEIPT = ReceiptScenario(
    receipt_key=f"{TEST_SCENARIO_ID}-receipt-1",
    quantity=Decimal("2"),
)

SECOND_RECEIPT = ReceiptScenario(
    receipt_key=f"{TEST_SCENARIO_ID}-receipt-2",
    quantity=Decimal("3"),
)

EXPECTED_FINAL_INVENTORY = Decimal("5")


CHAIN_CONTRACT = {
    "household_id": TEST_HOUSEHOLD_ID,
    "scenario_id": TEST_SCENARIO_ID,
    "product_name": TEST_PRODUCT_NAME,
    "target_location": {
        "location": TEST_LOCATION_NAME,
        "sublocation": TEST_SUBLOCATION_NAME,
    },
    "receipts": (
        {
            "receipt_key": FIRST_RECEIPT.receipt_key,
            "quantity": FIRST_RECEIPT.quantity,
        },
        {
            "receipt_key": SECOND_RECEIPT.receipt_key,
            "quantity": SECOND_RECEIPT.quantity,
        },
    ),
    "expected": {
        "global_product_linked": True,
        "product_type_linked": True,
        "inventory_quantity_after_first_receipt": Decimal("2"),
        "inventory_quantity_after_second_receipt": EXPECTED_FINAL_INVENTORY,
        "inventory_quantity_after_reprocessing_second_receipt": EXPECTED_FINAL_INVENTORY,
        "idempotent": True,
    },
    "isolation_rules": {
        "real_catalog_records_may_be_modified": False,
        "statistics_must_exclude_household_zero": True,
        "scenario_data_must_be_uniquely_identifiable": True,
    },
}


def validate_contract() -> None:
    """Fail fast wanneer het vaste PO-contract onbedoeld wordt gewijzigd."""

    assert TEST_HOUSEHOLD_ID == "0"
    assert FIRST_RECEIPT.quantity == Decimal("2")
    assert SECOND_RECEIPT.quantity == Decimal("3")
    assert FIRST_RECEIPT.quantity + SECOND_RECEIPT.quantity == EXPECTED_FINAL_INVENTORY
    assert CHAIN_CONTRACT["expected"]["inventory_quantity_after_reprocessing_second_receipt"] == Decimal("5")
    assert CHAIN_CONTRACT["isolation_rules"]["real_catalog_records_may_be_modified"] is False


if __name__ == "__main__":
    validate_contract()
    print("RECEIPT_INVENTORY_CHAIN_CONTRACT_GREEN")
