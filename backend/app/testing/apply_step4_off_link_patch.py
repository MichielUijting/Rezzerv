"""Pas Stap 4 deterministisch toe op off_product_link_service.py.

Dit script wijzigt uitsluitend de vooraf verwachte codefragmenten en stopt bij
iedere afwijking. Het is bedoeld voor eenmalige gecontroleerde uitvoering.
"""

from __future__ import annotations

from pathlib import Path

TARGET = Path("app/services/off_product_link_service.py")

OLD_IMPORT = '''from app.services.external_article_product_link_service import (
    save_external_article_product_link,
)
'''
NEW_IMPORT = '''from app.services.external_article_confirmation_service import (
    confirm_external_article_for_receipt_item,
)
'''

OLD_RECEIPT_TABLE_CONFIRM = '''
        confirmed_link = save_external_article_product_link(
            conn,
            retailer_code=row.get("retailer_code"),
            receipt_text=row.get("receipt_text"),
            external_article_code=row.get("external_article_code"),
            global_product_id=global_product_id,
            confirmed_by="external_databases_off_link",
        )

        return {
            "receipt_item_type": "receipt_table_line",
            "source_id": source_id,
            "household_article_id": article_id,
            "external_article_product_link": confirmed_link,
        }
'''
NEW_RECEIPT_TABLE_RETURN = '''
        return {
            "receipt_item_type": "receipt_table_line",
            "source_id": source_id,
            "household_article_id": article_id,
        }
'''

OLD_CALL = '''        receipt_link = _link_receipt_item(conn, receipt_item_id, global_product_id)
        if force_failure_after_link:
'''
NEW_CALL = '''        receipt_link = _link_receipt_item(conn, receipt_item_id, global_product_id)
        confirmed_external_link = confirm_external_article_for_receipt_item(
            conn,
            receipt_item_id=receipt_item_id,
            global_product_id=global_product_id,
            confirmed_by="external_databases_off_link",
        )
        receipt_link["external_article_product_link"] = confirmed_external_link
        if force_failure_after_link:
'''


def replace_exact_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: verwacht 1 voorkomen, gevonden {count}")
    return content.replace(old, new, 1)


def main() -> None:
    content = TARGET.read_text(encoding="utf-8")
    updated = replace_exact_once(content, OLD_IMPORT, NEW_IMPORT, "import")
    updated = replace_exact_once(
        updated,
        OLD_RECEIPT_TABLE_CONFIRM,
        NEW_RECEIPT_TABLE_RETURN,
        "oude receipt-table bevestiging",
    )
    updated = replace_exact_once(updated, OLD_CALL, NEW_CALL, "centrale bevestigingsaanroep")

    if "save_external_article_product_link" in updated:
        raise RuntimeError("Oude directe opslagaanroep is nog aanwezig")
    if updated.count("confirm_external_article_for_receipt_item(") != 1:
        raise RuntimeError("Nieuwe centrale bevestigingsaanroep is niet exact één keer aanwezig")

    TARGET.write_text(updated, encoding="utf-8", newline="\n")
    print("PATCH_TOEGEPAST=JA")
    print(f"BESTAND={TARGET}")


if __name__ == "__main__":
    main()
