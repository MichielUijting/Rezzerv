"""Pas Stap 6 gecontroleerd toe op de Kassa-aanmaakroute.

De Kassa-regel mag bij aanmaak geen parallelle productzoeker meer gebruiken.
Na invoegen bepaalt sync_receipt_table_line_product_links uitsluitend via de
centrale external_article_product_links-tabel of een product gekoppeld is.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "backend/app/main.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: verwacht exact 1 match, gevonden {count}")
    return text.replace(old, new, 1)


source = TARGET.read_text(encoding="utf-8")

old_lookup = '''        # Een universele barcode is leidend. De winkelartikelcode blijft hooguit
        # als aanvullende of historische identiteit beschikbaar.
        existing_product = find_global_product_match_for_receipt_line(
            conn,
            normalized_barcode,
            payload.article_name,
            external_article_code=normalized_external_article_code,
            retailer_code=existing.get('store_name'),
        )
        matched_global_product_id = (
            str(existing_product.get('id') or '').strip()
            if existing_product
            else None
        )
        article_match_status = 'product_matched' if matched_global_product_id else 'unmatched'
        confidence_score = (
            float(existing_product.get('confidence_score') or 1.0)
            if existing_product
            else None
        )
'''

new_lookup = '''        # Kassa start zonder lokale of kandidaatgebaseerde productmatch.
        # Na invoegen leest sync_receipt_table_line_product_links uitsluitend
        # de actieve centrale koppeling uit external_article_product_links.
        matched_global_product_id = None
        article_match_status = 'unmatched'
        confidence_score = None
'''

source = replace_once(source, old_lookup, new_lookup, "oude Kassa-productzoeker")

required_sync = '''        sync_receipt_table_line_product_links(
            conn,
            receipt_table_id,
            inserted_line_id,
            create_global_product=False,
            create_household_article=False,
        )
'''
if source.count(required_sync) != 1:
    raise RuntimeError("centrale synchronisatie na aanmaak ontbreekt of is niet uniek")

TARGET.write_text(source, encoding="utf-8", newline="\n")
print("PATCH_TOEGEPAST=JA")
print(f"BESTAND={TARGET.relative_to(ROOT)}")
