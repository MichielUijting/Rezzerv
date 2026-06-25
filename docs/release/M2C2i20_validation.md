# M2C2i-20 — Validatie

## Doelvalidatie

Aantonen dat bonartikelen met een externe artikelcode niet opnieuw door de kandidaatzoekflow gaan.

## Technische smoke zonder pytest

De backend-container bevat geen pytest. Gebruik daarom een gewone Python-smoke via stdin.

```powershell
@'
from app.services import external_database_matchflow_evidence as m

resolved = {
    "is_receipt_item_placeholder": True,
    "purchase_import_line_id": "pil-1",
    "receipt_line_text": "Veldsla",
    "retailer_code": "lidl",
    "retailer_article_number": "lidl:groente.veldsla",
}

unresolved = {
    "is_receipt_item_placeholder": True,
    "purchase_import_line_id": "pil-2",
    "receipt_line_text": "Nieuw onbekend artikel",
    "retailer_code": "lidl",
}

assert m.is_m2c2i20_external_resolved_item(resolved) is True
assert m.m2c2i20_external_product_code(resolved) == "lidl:groente.veldsla"
assert m.is_m2c2i20_external_resolved_item(unresolved) is False

unresolved_items, resolved_items = m._m2c2i20_split_resolved_items([resolved, unresolved])

assert unresolved_items == [unresolved]
assert resolved_items == [resolved]

result = m._m2c2i20_enrich_ensure_result(
    {
        "ok": True,
        "total": 1,
        "processed": 1,
        "saved_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "errors": [],
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    },
    original_total=2,
    resolved_items=resolved_items,
)

assert result["total"] == 2
assert result["external_resolved_skipped_count"] == 1
assert result["external_resolved_skipped"][0]["external_product_code"] == "lidl:groente.veldsla"
assert result["m2c2i20_resolved_state_gate"] is True
assert result["creates_global_product"] is False
assert result["creates_household_article"] is False
assert result["creates_inventory_event"] is False

print("M2C2i-20 smoke OK: resolved bonartikelen worden niet opnieuw gezocht.")
'@ | docker compose exec -T backend python
```

Verwacht:

```text
M2C2i-20 smoke OK: resolved bonartikelen worden niet opnieuw gezocht.
```

## Functionele test in Externe databases

1. Open `http://localhost:5174/externe-databases`.
2. Controleer een bonartikel dat al een artikelnummer/externe code heeft.
3. Klik op vernieuwen/kandidaten ophalen.
4. Controleer dat dit artikel niet opnieuw als onbekend kandidaatzoekitem wordt behandeld.
5. Controleer dat artikelen zonder externe code nog wel kandidaatzoekacties kunnen krijgen.

## Verwachte technische output

De ensure-flow geeft expliciet terug:

```json
{
  "m2c2i20_resolved_state_gate": true,
  "external_resolved_skipped_count": 1,
  "creates_global_product": false,
  "creates_household_article": false,
  "creates_inventory_event": false
}
```

## Releasebesluit

GO als:

- resolved bonregels worden overgeslagen;
- unresolved bonregels nog kandidaten kunnen ophalen;
- safety flags false blijven;
- bestaande Lidl-catalogus- en aliaslearningflow niet regressief wijzigt.
