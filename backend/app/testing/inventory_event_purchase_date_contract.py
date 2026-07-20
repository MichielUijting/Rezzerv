from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


def main() -> None:
    main_path = Path(__file__).resolve().parents[1] / "main.py"
    source = main_path.read_text(encoding="utf-8")

    require(
        "purchase_date TEXT" in source,
        "inventory_events bevat een afzonderlijk purchase_date-veld",
    )
    require(
        ":purchase_date, :supplier_name" in source,
        "create_inventory_event schrijft purchase_date naar inventory_events",
    )
    require(
        "created_at\n            ) VALUES" not in source
        or "CURRENT_TIMESTAMP" in source,
        "created_at blijft de technische verwerkingstijd",
    )
    require(
        "pib.raw_payload," in source,
        "voorraadverwerking leest de opgeslagen batchmetadata",
    )
    require(
        'purchase_date = str(batch_metadata.get("purchase_date") or "").strip() or None'
        in source,
        "voorraadverwerking haalt de aankoopdatum uit batchmetadata",
    )
    require(
        "purchase_date=purchase_date,\n"
        "                        article_number="
        in source,
        "inkoopbijboeking gebruikt de aankoopdatum",
    )
    require(
        "def create_auto_repurchase_event(" in source
        and "purchase_date: str | None = None," in source,
        "automatische afboeking accepteert de aankoopdatum",
    )
    require(
        "quantity=requested_deduction_quantity,\n"
        "                            purchase_date=purchase_date,"
        in source,
        "automatische afboeking ontvangt dezelfde aankoopdatum",
    )
    require(
        "note=f'Automatisch {quantity_label} afgeboekt bij herhaalaankoop.',\n"
        "        purchase_date=purchase_date,"
        in source,
        "automatische afboeking bewaart de aankoopdatum in inventory_events",
    )


if __name__ == "__main__":
    main()
