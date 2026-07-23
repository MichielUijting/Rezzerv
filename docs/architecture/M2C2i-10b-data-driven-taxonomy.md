# M2C2i-10b — Datagedreven taxonomie en kandidaatselectie

## Doel

Productkennis voor Externe databases, Uitpakken en kandidaatselectie wordt als data beheerd, niet als programmacode.

Deze stap verwijdert hardcoded categorie-, producttype- en variantkennis uit de receipt product analyzer. De analyzer gebruikt voortaan de taxonomie- en variantdata uit `backend/app/data/product_taxonomy_seed.json` en de generieke taxonomystore.

## Geraakt

- `backend/app/data/product_taxonomy_seed.json`
- `backend/app/services/product_taxonomy_store.py`
- `backend/app/services/receipt_product_intent_analyzer.py`
- `backend/tests/test_product_taxonomy_receipt_terms_m2c2i10a.py`

## Niet geraakt

- Geen frontendwijziging
- Geen UI-layoutwijziging
- Geen Open Food Facts live lookup
- Geen automatische global_product-aanmaak
- Geen household_article-mutatie
- Geen inventory_event-mutatie
- Geen release-zip

## Functionele regels

- Categorie komt uit `product_taxonomy.category` / seeddata.
- Producttype komt uit `product_taxonomy.product_type` / seeddata.
- Varianttermen komen uit `product_variant_terms` in seeddata.
- Searchable terms worden generiek opgebouwd uit ruwe bontekst, intent, categorie, producttype, varianttermen, variantzoektermen, hoeveelheid en tokens.
- Fallback- en unresolved-kandidaten blijven beslisondersteuning en mogen geen definitieve product- of voorraadmutatie veroorzaken.

## Acceptatiecriteria

- `Gouda belegen gerasp` wordt herkend als `zuivel.kaas`.
- `Crème frache 30%` wordt herkend als `zuivel.creme_fraiche`.
- `Gouda belegen gerasp` levert verrijkte zoektermen op zoals `gouda kaas`, `belegen kaas`, `geraspte kaas` en `kaas`.
- De receipt product analyzer bevat geen `PRODUCT_TYPE_BY_INTENT_PREFIX`, `CATEGORY_BY_INTENT_PREFIX` of `VARIANT_TERMS` meer.
- De frontend-regressie voor Kassa, Uitpakken en Externe databases blijft groen.

## Validatie

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github

git switch feature/m2c2i10b-data-driven-taxonomy

docker compose up -d --build
Invoke-RestMethod http://localhost:8011/api/health

@'
from app.services.receipt_product_intent_analyzer import analyze_receipt_product_line

cases = [
    "Gouda belegen gerasp",
    "Crème frache 30%",
]
for text in cases:
    analysis = analyze_receipt_product_line(text, retailer_code="lidl")
    print(text, "->", analysis)
'@ | docker compose exec -T backend python -

# indien pytest beschikbaar is:
docker compose exec -T backend pytest backend/tests/test_product_taxonomy_receipt_terms_m2c2i10a.py

.\scripts\run-frontend-regression-report.ps1 -SkipDockerBuild
```
