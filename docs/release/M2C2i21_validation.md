# M2C2i-21 — Validatie

## Doelvalidatie

Aantonen dat onbekende Lidl-bonregels lokale cataloguskandidaten kunnen krijgen uit `external_product_index`, zonder live externe bron en zonder product-/voorraadmutaties.

## Opstartroutine

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
git fetch origin
git switch m2c2i21-lidl-local-catalog-index
git pull --ff-only origin m2c2i21-lidl-local-catalog-index
docker compose up -d --build backend frontend
Start-Sleep -Seconds 90
```

## Smoke zonder pytest

```powershell
@'
from app.services.lidl_local_catalog_index import ensure_lidl_local_catalog_index, search_lidl_local_catalog_candidates
from app.services import external_database_matchflow_evidence as m

loaded = ensure_lidl_local_catalog_index()
assert loaded["loaded_count"] > 0
assert loaded["creates_global_product"] is False
assert loaded["creates_household_article"] is False
assert loaded["creates_inventory_event"] is False

catalog_candidates = search_lidl_local_catalog_candidates("Veldsla", limit=5)
assert catalog_candidates
assert len(catalog_candidates) <= 5
assert catalog_candidates[0]["candidate_source_name"] == "lidl_catalog_index"
assert catalog_candidates[0]["creates_global_product"] is False
assert catalog_candidates[0]["creates_household_article"] is False
assert catalog_candidates[0]["creates_inventory_event"] is False

match = m.match_retailer_receipt_line("lidl", "Veldsla", include_below_threshold=True)
assert match["uses_lidl_local_catalog_index"] is True
assert match["lidl_local_catalog_candidate_count"] >= 1
assert len(match["candidates"]) <= 5
assert any(c["candidate_source_name"] == "lidl_catalog_index" for c in match["candidates"])
assert match["creates_global_product"] is False
assert match["creates_household_article"] is False
assert match["creates_inventory_event"] is False

print("M2C2i-21 smoke OK: lokale Lidl-catalogusindex levert kandidaten zonder mutaties.")
'@ | docker compose exec -T backend python
```

Verwacht:

```text
M2C2i-21 smoke OK: lokale Lidl-catalogusindex levert kandidaten zonder mutaties.
```

## PO-test in de UI

1. Open `http://localhost:5174/externe-databases`.
2. Gebruik een Lidl-bonregel die nog geen externe artikelcode heeft maar wel als product in de Lidl-catalogusdata voorkomt.
3. Ververs/haal kandidaten op.
4. Controleer dat maximaal 5 kandidaten worden getoond.
5. Controleer dat minimaal één kandidaat bron `lidl_catalog_index` heeft.
6. Controleer dat er geen Mijn-artikel wordt aangemaakt.
7. Controleer dat er geen voorraadmutatie ontstaat.

## GO-criteria

- Onbekende Lidl-bonregel krijgt cataloguskandidaat uit lokale index.
- Kandidaten zijn maximaal 5.
- Bron is herkenbaar als `lidl_catalog_index`.
- Geen live externe afhankelijkheid.
- Geen global product, household article of inventory event.
