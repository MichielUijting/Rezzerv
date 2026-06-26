# M2C2i-19R — Validatie

## Doelvalidatie

Aantonen dat Rezzerv een onbekende bonregel on the fly als conceptkandidaat in `external_product_index` kan leren, zonder JSON handmatig te wijzigen en zonder product-/voorraadmutaties.

## Opstartroutine

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
git fetch origin
git switch m2c2i19r-data-driven-candidates
git pull --ff-only origin m2c2i19r-data-driven-candidates
docker compose up -d --build backend frontend
Start-Sleep -Seconds 90
```

## Smoke zonder pytest

```powershell
@'
from app.db import engine
from sqlalchemy import text
from app.services.external_product_index_store import ensure_learned_external_product_candidate, search_external_product_index_candidates
from app.services.external_database_matchflow_evidence import match_retailer_receipt_line

receipt_text = "M2C2i19R onbekende testregel"
retailer_code = "lidl"

with engine.begin() as conn:
    conn.execute(
        text("DELETE FROM external_product_index WHERE source_name = 'learned_receipt_line' AND product_name = :name"),
        {"name": receipt_text},
    )

learned = ensure_learned_external_product_candidate(receipt_text, retailer_code=retailer_code)
assert learned["ok"] is True
assert learned["learned"] is True
assert learned["item"]["source_name"] == "learned_receipt_line"
assert learned["creates_global_product"] is False
assert learned["creates_household_article"] is False
assert learned["creates_inventory_event"] is False

rows = search_external_product_index_candidates(receipt_text, retailer_code=retailer_code, limit=10)
assert rows
assert any(row.get("source_name") == "learned_receipt_line" for row in rows)

match = match_retailer_receipt_line(retailer_code, receipt_text, include_below_threshold=True)
assert match["candidates"]
assert len(match["candidates"]) <= 5
assert any(candidate.get("candidate_source_name") == "learned_receipt_line" for candidate in match["candidates"])
assert match["creates_global_product"] is False
assert match["creates_household_article"] is False
assert match["creates_inventory_event"] is False

second = ensure_learned_external_product_candidate(receipt_text, retailer_code=retailer_code)
assert second["ok"] is True
assert second["learned"] is False
assert second["reason"] == "already_exists"

print("M2C2i-19R smoke OK: onbekende bonregel wordt on the fly geleerd zonder JSON- of productmutaties.")
'@ | docker compose exec -T backend python
```

Verwacht:

```text
M2C2i-19R smoke OK: onbekende bonregel wordt on the fly geleerd zonder JSON- of productmutaties.
```

## PO-test

1. Open `http://localhost:5174/externe-databases`.
2. Gebruik de bestaande UI, geen nieuwe frontend.
3. Gebruik een onbekend bonartikel.
4. Laat kandidaten ophalen.
5. Controleer dat een conceptkandidaat verschijnt.
6. Controleer dat dezelfde regel daarna niet opnieuw als nieuw hoeft te worden geleerd.
7. Controleer dat performance bij pagina bijlezen acceptabel blijft.
8. Controleer dat er geen Mijn artikel en geen voorraadmutatie ontstaat.

## GO-criteria

- Onbekende bonregel wordt on the fly geleerd in `external_product_index`.
- Geen handmatige JSON-uitbreiding nodig.
- Geen runtime-write naar Git-/bron-JSON.
- De tweede keer komt dezelfde kandidaat uit de database terug.
- Geen Python-codewijziging nodig per nieuw artikel.
- Geen nieuwe frontend.
- Geen merkbare performanceverslechtering bij paginawissel.
- Geen `global_products`-aanmaak.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
