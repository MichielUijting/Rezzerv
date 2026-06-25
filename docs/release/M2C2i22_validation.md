# M2C2i-22 — Validatie

## Doelvalidatie

Aantonen dat een externe kandidaat kan worden bevestigd op een bonregel/importregel, zonder `global_products`, Mijn artikel of voorraadmutaties aan te maken.

## Opstartroutine

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
git fetch origin
git switch m2c2i22-confirm-external-candidate
git pull --ff-only origin m2c2i22-confirm-external-candidate
docker compose up -d --build backend frontend
Start-Sleep -Seconds 90
```

## Smoke zonder pytest

Deze smoke maakt tijdelijk alleen een candidate aan en bevestigt die. Daarmee testen we de kernregel: de candidate wordt external resolved, zonder `global_product_id` of andere product-/voorraadmutaties. In de echte UI-flow wordt dezelfde functie gebruikt met een bestaande `purchase_import_line_id`, waardoor ook de externe artikelcode op de importregel wordt vastgelegd als de kolom bestaat.

```powershell
@'
from app.db import engine
from sqlalchemy import text
from app.services.external_product_candidate_store import ensure_external_product_candidates_schema
from app.services.external_candidate_confirmation import confirm_external_candidate_for_receipt_item

ensure_external_product_candidates_schema()
line_id = "m2c2i22-smoke-line"
candidate_id = "m2c2i22-smoke-candidate"
context_key = "purchase-import-line:" + line_id

with engine.begin() as conn:
    conn.execute(text("DELETE FROM external_product_candidates WHERE id = :id OR purchase_import_line_id = :line_id"), {"id": candidate_id, "line_id": line_id})
    conn.execute(text("""
        INSERT INTO external_product_candidates (
            id, purchase_import_line_id, context_key, retailer_code, receipt_line_text,
            candidate_name, candidate_brand, candidate_source_name, candidate_source_product_code,
            source_name, source_product_code, retailer_article_number, score,
            candidate_status, is_probable, is_user_confirmed, is_external_database_override,
            created_by, created_at, updated_at
        ) VALUES (
            :id, :purchase_import_line_id, :context_key, 'lidl', 'Veldsla',
            'Lidl Veldsla', 'Lidl Groente', 'lidl_catalog_index', 'lidl:groente.veldsla',
            'lidl_catalog_index', 'lidl:groente.veldsla', 'lidl:groente.veldsla', 0.95,
            'possible_candidate', 1, 0, 0,
            'm2c2i22_smoke', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """), {"id": candidate_id, "purchase_import_line_id": line_id, "context_key": context_key})

result = confirm_external_candidate_for_receipt_item(candidate_id)
assert result["ok"] is True
assert result["confirmed"] is True
assert result["external_product_code"] == "lidl:groente.veldsla"
assert result["creates_global_product"] is False
assert result["creates_household_article"] is False
assert result["creates_inventory_event"] is False

with engine.begin() as conn:
    candidate = conn.execute(text("SELECT candidate_status, status, global_product_id, is_user_confirmed FROM external_product_candidates WHERE id = :id"), {"id": candidate_id}).mappings().first()
    assert candidate["candidate_status"] == "user_confirmed"
    assert candidate["status"] == "external_resolved"
    assert not candidate["global_product_id"]
    assert int(candidate["is_user_confirmed"] or 0) == 1

print("M2C2i-22 smoke OK: externe kandidaat bevestigd zonder product- of voorraadmutaties.")
'@ | docker compose exec -T backend python
```

Verwacht:

```text
M2C2i-22 smoke OK: externe kandidaat bevestigd zonder product- of voorraadmutaties.
```

## GO-criteria

- Geselecteerde candidate wordt `user_confirmed` / `external_resolved`.
- Externe artikelcode is vastgelegd op de bonregel/importregel als de kolom bestaat.
- `global_product_id` blijft leeg.
- Geen `global_products`-aanmaak.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
