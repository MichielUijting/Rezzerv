# M2C2i-3 — Lidl-taxonomie als OFF-querybasis

## Doel

Deze stap zet de bestaande Lidl-matchpreview om naar een uitbreidbare taxonomielaag. De taxonomie maakt uit een kort of afgekapt Lidl-bonartikel reviewbare zoektermen voor Open Food Facts.

## Scope

Toegevoegd:

- `backend/app/services/external_retailer_taxonomy.py`
- `backend/tests/test_external_retailer_taxonomy.py`

De service bevat:

- Lidl-synoniemen en afkortingen, bijvoorbeeld `kruidenm` → `kruidenmix` / `specerijenmix`.
- Lidl-huismerken, bijvoorbeeld Kania, Kanig, El Tequito en Milbona.
- Taxonomie-items voor Mexicaanse kruidenmix en Taco Sauce.
- Reviewbare OFF-querytermen per taxonomie-item.

## Expliciet niet gewijzigd

- Geen automatische Open Food Facts-live lookup.
- Geen aanmaak van `global_products`.
- Geen aanmaak van `household_articles`.
- Geen voorraadmutatie.
- Geen wijziging aan Kassa-statuslogica.
- Geen wijziging aan Uitpakken-verwerking.

## Verwacht gedrag

Voor Lidl-bonregel:

```text
Mexicaanse kruidenm.
```

levert de querybasis onder andere termen op zoals:

```text
mexicaanse kruidenm
kania taco specerijenmix
kanig taco kruidenmix
taco seasoning mix
```

Deze termen zijn bedoeld om later betere OFF-index- of OFF-zoekresultaten te krijgen, maar zijn nog geen definitieve productkoppeling.

## Technische controle

Gerichte smoke-test zonder extra Python-afhankelijkheden:

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
$env:PYTHONPATH = ".\backend"

@'
from app.services.external_retailer_taxonomy import (
    build_off_query_terms,
    expand_receipt_terms,
    get_taxonomy_summary,
    list_taxonomy_entries,
)

summary = get_taxonomy_summary("Lidl")
assert summary["retailer_code"] == "lidl"
assert summary["taxonomy_entry_count"] >= 5
assert summary["creates_global_product"] is False
assert summary["creates_household_article"] is False
assert summary["creates_inventory_event"] is False

terms = expand_receipt_terms("Mexicaanse kruidenm.", "lidl")
assert "mexicaanse kruidenm" in terms
assert any("kruidenmix" in term for term in terms)
assert any("specerijenmix" in term for term in terms)

off_terms = build_off_query_terms("Mexicaanse kruidenm.", "lidl")
assert "kania taco specerijenmix" in off_terms
assert "kanig taco kruidenmix" in off_terms
assert "taco seasoning mix" in off_terms

entries = list_taxonomy_entries("lidl")
assert entries
assert all(entry.retailer_code == "lidl" for entry in entries)

print("M2C2i-3 taxonomy smoke OK")
'@ | python -
```

Bij vervolgwijziging richting Externe databases UI/API blijft verplicht:

```powershell
.\scripts\run-frontend-regression-report.ps1 -SkipDockerBuild
```

Verwacht: frontend-regressie 7/7 groen.

## PO-controle

1. Open later de Externe databases-flow.
2. Kies of bekijk een Lidl-bonartikel zoals `Mexicaanse kruidenm.` of `Taco saus`.
3. Controleer dat de kandidaatvorming geen voorraadmutatie uitvoert.
4. Controleer dat er geen nieuw Mijn artikel ontstaat zonder expliciete verwerking.
5. Controleer dat de zoektermen logisch beter zijn dan alleen de ruwe bontekst.
