# M2C2i-19R — Validatie

## Doelvalidatie

Aantonen dat nieuwe artikelkandidaten uit data kunnen komen, zonder codewijziging per artikel en zonder product-/voorraadmutaties.

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
from app.services.external_product_index_store import ensure_external_product_index_seeded, search_external_product_index_candidates
from app.services.external_database_matchers import match_retailer_receipt_line

seed = ensure_external_product_index_seeded(force=True)
assert seed["ok"] is True
assert seed["inserted"] > 0
assert seed["creates_global_product"] is False
assert seed["creates_household_article"] is False
assert seed["creates_inventory_event"] is False

rows = search_external_product_index_candidates("linguin", retailer_code="lidl", limit=10)
assert rows
assert any("linguine" in (row.get("product_name") or "").lower() for row in rows)

match = match_retailer_receipt_line("lidl", "linguin", include_below_threshold=True)
assert match["candidates"]
assert len(match["candidates"]) <= 5
assert any("linguine" in (candidate.get("candidate_name") or "").lower() for candidate in match["candidates"])
assert match["creates_global_product"] is False
assert match["creates_household_article"] is False
assert match["creates_inventory_event"] is False

second_seed = ensure_external_product_index_seeded()
assert second_seed["seeded"] is False

print("M2C2i-19R smoke OK: data-index levert kandidaten zonder product- of voorraadmutaties.")
'@ | docker compose exec -T backend python
```

Verwacht:

```text
M2C2i-19R smoke OK: data-index levert kandidaten zonder product- of voorraadmutaties.
```

## PO-test

1. Open `http://localhost:5174/externe-databases`.
2. Gebruik de bestaande UI, geen nieuwe frontend.
3. Controleer dat een onbekend Lidl-bonartikel met tekst `linguin` zinvolle kandidaten kan tonen.
4. Controleer dat de performance bij pagina bijlezen acceptabel blijft.
5. Controleer dat er geen Mijn artikel en geen voorraadmutatie ontstaat.

## GO-criteria

- Kandidaten komen uit `external_product_index`.
- Extra kandidaatdata kan via JSON onder `backend/app/data/external_product_index/` worden toegevoegd.
- Geen Python-codewijziging nodig per nieuw artikel.
- Geen nieuwe frontend.
- Geen merkbare performanceverslechtering bij paginawissel.
- Geen `global_products`-aanmaak.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
