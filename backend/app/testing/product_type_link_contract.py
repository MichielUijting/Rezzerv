from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from sqlalchemy import text


def run_contract() -> dict:
    with tempfile.TemporaryDirectory(prefix="rezzerv_product_type_contract_") as tmp_dir:
        database_path = Path(tmp_dir) / "product-type.sqlite"
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

        backend_root = Path(__file__).resolve().parents[2]
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        for module_name in [name for name in list(sys.modules) if name == "app" or name.startswith("app.")]:
            del sys.modules[module_name]

        main = importlib.import_module("app.main")
        from app.services.product_inventory_group_store import (
            ensure_product_inventory_group_schema,
            link_global_product_to_inventory_group,
        )

        ensure_product_inventory_group_schema()

        global_product_id = "chain-global-product"
        with main.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO global_products (
                        id, name, primary_gtin, brand, source, status
                    ) VALUES (
                        :id, :name, :gtin, :brand, :source, :status
                    )
                    """
                ),
                {
                    "id": global_product_id,
                    "name": "AH BANANEN",
                    "gtin": "8710000091001",
                    "brand": "Albert Heijn",
                    "source": "test",
                    "status": "active",
                },
            )

        result = link_global_product_to_inventory_group(
            global_product_id=global_product_id,
            inventory_group_key="groente.courgette",
            confidence=1.0,
            source="receipt_inventory_chain",
            confirmed_by_user=True,
        )
        assert bool(result.get("ok")), f"Producttypekoppeling mislukt: {result}"

        with main.engine.begin() as conn:
            count = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM product_group_memberships
                        WHERE global_product_id = :global_product_id
                          AND inventory_group_key = :inventory_group_key
                          AND COALESCE(active, 1) = 1
                        """
                    ),
                    {
                        "global_product_id": global_product_id,
                        "inventory_group_key": "groente.courgette",
                    },
                ).scalar()
                or 0
            )

        assert count == 1, f"Verwacht exact één actieve producttypekoppeling, gevonden: {count}"
        return {
            "status": "passed",
            "global_product_id": global_product_id,
            "product_type_link_count": count,
            "production_service": True,
        }


if __name__ == "__main__":
    try:
        print(run_contract())
        print("PRODUCT_TYPE_LINK_CONTRACT_GREEN")
    except Exception as exc:
        print(f"PRODUCT_TYPE_LINK_CONTRACT_FAILURE|{exc.__class__.__name__}|{exc}")
        raise SystemExit(1)
