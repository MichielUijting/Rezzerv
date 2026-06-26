# M2C2i-20R — Validatie

## Doelvalidatie

Aantonen dat een onbekende bonregel als conceptkandidaat wordt geleerd en via de bestaande candidate-save/ensure-flow in `external_product_candidates` terechtkomt.

## Opstartroutine

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
git fetch origin
git switch m2c2i20r-concept-candidates-ui-flow
git pull --ff-only origin m2c2i20r-concept-candidates-ui-flow
docker compose up -d --build backend frontend
Start-Sleep -Seconds 90
```

## Smoke zonder pytest

```powershell
@'
from app.db import engine
from sqlalchemy import text
from app.services.external_product_candidate_store import build_candidate_context_key, list_saved_external_product_candidates
from app.services.external_database_matchflow_evidence import ensure_external_receipt_item_candidates

receipt_text = "M2C2i20R onbekende UI flow testregel"
retailer_code = "lidl"
line_id = "m2c2i20r-smoke-line"
context_key = build_candidate_context_key(retailer_code, receipt_text, purchase_import_line_id=line_id)

with engine.begin() as conn:
    conn.execute(text("DELETE FROM external_product_candidates WHERE context_key = :context_key"), {"context_key": context_key})
    conn.execute(text("DELETE FROM external_product_index WHERE source_name = 'learned_receipt_line' AND product_name = :name"), {"name": receipt_text})

result = ensure_external_receipt_item_candidates(
    items=[{
        "retailer_code": retailer_code,
        "receipt_line_text": receipt_text,
        "purchase_import_line_id": line_id,
    }],
    include_below_threshold=True,
)

assert result["ok"] is True
assert result["processed"] == 1
assert result["saved_count"] >= 1 or result["updated_count"] >= 1
assert result["creates_global_product"] is False
assert result["creates_household_article"] is False
assert result["creates_inventory_event"] is False

saved = list_saved_external_product_candidates(context_key=context_key, limit=10)
items = saved["items"]
assert items
assert any(item.get("candidate_source_name") == "learned_receipt_line" for item in items)
assert any(item.get("candidate_status") == "concept_candidate" for item in items)
assert all(not item.get("global_product_id") for item in items)

second = ensure_external_receipt_item_candidates(
    items=[{
        "retailer_code": retailer_code,
        "receipt_line_text": receipt_text,
        "purchase_import_line_id": line_id,
    }],
    include_below_threshold=True,
)
assert second["ok"] is True
assert second["saved_count"] == 0
assert second["creates_global_product"] is False
assert second["creates_household_article"] is False
assert second["creates_inventory_event"] is False

print("M2C2i-20R smoke OK: conceptkandidaat komt in bestaande candidate-flow zonder productmutaties.")
'@ | docker compose exec -T backend python
```

Verwacht:

```text
M2C2i-20R smoke OK: conceptkandidaat komt in bestaande candidate-flow zonder productmutaties.
```

## PO-test

1. Open `http://localhost:5174/externe-databases`.
2. Gebruik de bestaande UI.
3. Kies een onbekend bonartikel.
4. Klik de bestaande actie om kandidaten bij te lezen.
5. Controleer dat er een kandidaat verschijnt.
6. Controleer dat er geen Mijn artikel en geen voorraadmutatie ontstaat.

## GO-criteria

- Onbekende bonregel levert een `concept_candidate` op.
- De kandidaat staat in `external_product_candidates`.
- De kandidaat gebruikt bron `learned_receipt_line`.
- De tweede run maakt geen dubbele nieuwe kandidaat.
- Geen nieuwe frontend.
- Geen `global_products`-aanmaak.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
