# M2C2i-21S — Validatie

## Doelvalidatie

Aantonen dat `Argentijnse Malbec` wordt herkend als wijn, zonder fallback-kandidaat en zonder database-write.

## Opstartroutine

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
git fetch origin
git switch m2c2i21s-wine-intent-no-fallback
git pull --ff-only origin m2c2i21s-wine-intent-no-fallback
docker compose up -d --build backend frontend
Start-Sleep -Seconds 90
```

## Smoke zonder pytest

```powershell
@'
from app.services.external_candidate_diagnostics import diagnose_real_candidate_coverage

result = diagnose_real_candidate_coverage(
    retailer_code='lidl',
    receipt_line_text='Argentijnse Malbec',
    include_below_threshold=True,
)

analysis = result['receipt_analysis']
assert result['ok'] is True
assert result['writes_database'] is False
assert result['creates_global_product'] is False
assert result['creates_household_article'] is False
assert result['creates_inventory_event'] is False
assert result['uses_coverage_fallback'] is False
assert result['uses_legacy_fallback'] is False
assert result['has_forbidden_fallback_candidate'] is False
assert result['forbidden_candidate_count'] == 0

assert analysis['product_intent'] == 'wijn'
assert analysis['category'] == 'wijn'
assert analysis['product_type'] == 'rode wijn'
assert 'malbec' in analysis['variant_terms']
assert 'argentijnse' in analysis['variant_terms']
assert analysis['retailer_catalog_matched'] is False

assert result['real_candidate_count'] == 0
assert result['candidate_count'] == 0
assert result['candidate_source'] in {'no_real_candidate', 'external_product_index_no_match'}

print('M2C2i-21S smoke OK: Argentijnse Malbec wordt wijn-intent zonder fallback-kandidaat.')
'@ | docker compose exec -T backend python
```

Verwacht:

```text
M2C2i-21S smoke OK: Argentijnse Malbec wordt wijn-intent zonder fallback-kandidaat.
```

## API-test

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8011/api/external-databases/retailers/lidl/diagnose-real-candidates" `
  -ContentType "application/json" `
  -Body '{"receipt_line_text":"Argentijnse Malbec","include_below_threshold":true}'
```

Controleer:

```text
receipt_analysis.product_intent = wijn
receipt_analysis.product_type = rode wijn
receipt_analysis.variant_terms bevat malbec en argentijnse
real_candidate_count = 0
candidate_count = 0
uses_coverage_fallback = false
writes_database = false
```

## GO-criteria

- `Argentijnse Malbec` wordt als wijn geduid.
- Er wordt geen kandidaat gemaakt zolang echte brondata ontbreekt.
- Geen fallback.
- Geen self-learning.
- Geen database-write.
- Geen frontendwijziging.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
