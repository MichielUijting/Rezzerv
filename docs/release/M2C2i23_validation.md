# M2C2i-23 — Validatie

## Doelvalidatie

Aantonen dat de Externe databases-UI bevestigde herkenningen zichtbaar maakt als `Herkenning bevestigd`, en dat bevestigen geen product-/voorraadmutaties veroorzaakt.

## Opstartroutine

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
git fetch origin
git switch m2c2i23-confirmed-external-candidate-ui
git pull --ff-only origin m2c2i23-confirmed-external-candidate-ui
docker compose up -d --build backend frontend
Start-Sleep -Seconds 90
```

## Smoke zonder pytest

```powershell
@'
from app.db import engine
from sqlalchemy import text
from app.services.external_product_candidate_store import ensure_external_product_candidates_schema
from app.services.external_candidate_confirmation import confirm_external_candidate_for_receipt_item

ensure_external_product_candidates_schema()
line_id = "m2c2i23-smoke-line"
candidate_id = "m2c2i23-smoke-candidate"
context_key = "purchase-import-line:" + line_id

with engine.begin() as conn:
    conn.execute(text("DELETE FROM external_product_candidates WHERE id = :id OR purchase_import_line_id = :line_id"), {"id": candidate_id, "line_id": line_id})
    conn.execute(text("""
        INSERT INTO external_product_candidates (
            id, purchase_import_line_id, context_key, retailer_code, receipt_line_text,
            candidate_name, candidate_brand, candidate_source_name, candidate_source_product_code,
            source_name, source_product_code, retailer_article_number, score,
            candidate_status, status, is_probable, is_user_confirmed, is_external_database_override,
            created_by, created_at, updated_at
        ) VALUES (
            :id, :purchase_import_line_id, :context_key, 'lidl', 'Veldsla',
            'Lidl Veldsla', 'Lidl Groente', 'lidl_catalog_index', 'lidl:groente.veldsla',
            'lidl_catalog_index', 'lidl:groente.veldsla', 'lidl:groente.veldsla', 0.95,
            'possible_candidate', 'candidate', 1, 0, 0,
            'm2c2i23_smoke', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
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
    row = conn.execute(text("SELECT candidate_status, status, retailer_article_number, global_product_id, is_user_confirmed FROM external_product_candidates WHERE id = :id"), {"id": candidate_id}).mappings().first()
    assert row["candidate_status"] == "user_confirmed"
    assert row["status"] == "external_resolved"
    assert row["retailer_article_number"] == "lidl:groente.veldsla"
    assert not row["global_product_id"]
    assert int(row["is_user_confirmed"] or 0) == 1

print("M2C2i-23 smoke OK: herkenning bevestigd zonder product- of voorraadmutaties.")
'@ | docker compose exec -T backend python
```

Verwacht:

```text
M2C2i-23 smoke OK: herkenning bevestigd zonder product- of voorraadmutaties.
```

## PO-test in de UI

1. Open `http://localhost:5174/externe-databases`.
2. De sectie heet `Bonartikelen herkennen`.
3. Dubbelklik een bonartikel met herkenningskandidaten.
4. Selecteer een herkenningskandidaat.
5. Klik `Bevestig herkenning`.
6. Controleer dat de status in de tabel `Herkenning bevestigd` wordt.
7. Controleer dat de `Winkel-/broncode` zichtbaar blijft.
8. Klik `Herkenningskandidaten bijlezen` of `Vernieuwen`.
9. Controleer dat de status `Herkenning bevestigd` behouden blijft.

## GO-criteria

- Bevestigde kandidaat is zichtbaar als `Herkenning bevestigd`.
- Winkel-/broncode is zichtbaar in de hoofdregel.
- Detailkandidaat toont bron en winkel-/broncode.
- Refresh veroorzaakt geen nieuwe kandidaatzoeking voor bevestigde herkenningen.
- Geen `global_products`-aanmaak.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
