# M2C2i-20S — Validatie

## Doelvalidatie

Aantonen dat Rezzerv uitlegt waarom een bonregel geen echte kandidaat heeft, zonder fallback te maken en zonder database te wijzigen.

## Opstartroutine

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
git fetch origin
git switch m2c2i20s-real-candidate-diagnostics
git pull --ff-only origin m2c2i20s-real-candidate-diagnostics
docker compose up -d --build backend frontend
Start-Sleep -Seconds 90
```

## Smoke zonder pytest

```powershell
@'
from app.services.external_candidate_diagnostics import diagnose_real_candidate_coverage

result = diagnose_real_candidate_coverage(
    retailer_code='lidl',
    receipt_line_text='M2C2i20S onbekend geen echte match',
    include_below_threshold=True,
)

assert result['ok'] is True
assert result['writes_database'] is False
assert result['creates_global_product'] is False
assert result['creates_household_article'] is False
assert result['creates_inventory_event'] is False
assert result['uses_coverage_fallback'] is False
assert result['uses_legacy_fallback'] is False
assert result['has_forbidden_fallback_candidate'] is False
assert result['forbidden_candidate_count'] == 0
assert 'diagnostic_reasons' in result
assert 'index_probe' in result
assert 'receipt_analysis' in result

print('M2C2i-20S smoke OK: diagnose verklaart kandidaatdekking zonder fallback of writes.')
'@ | docker compose exec -T backend python
```

Verwacht:

```text
M2C2i-20S smoke OK: diagnose verklaart kandidaatdekking zonder fallback of writes.
```

## API-smoke

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8011/api/external-databases/retailers/lidl/diagnose-real-candidates" `
  -ContentType "application/json" `
  -Body '{"receipt_line_text":"M2C2i20S onbekend geen echte match","include_below_threshold":true}'
```

Controleer in de output:

```text
writes_database = false
has_forbidden_fallback_candidate = false
diagnostic_reasons bevat waarom er geen echte kandidaat is
```

## PO-test

1. Kies een Lidl-bonregel zonder kandidaat.
2. Draai de diagnose via API-smoke met die exacte tekst.
3. Bekijk:
   - `index_probe.search_probe_rows`
   - `receipt_analysis.product_intent`
   - `diagnostic_reasons`
4. Geen kandidaat betekent nu: er ontbreekt echte brondekking of de echte match scoort niet goed genoeg.

## GO-criteria

- Diagnose werkt zonder database-writes.
- Geen fallback of conceptkandidaat wordt teruggegeven.
- Verboden fallbacktypes worden expliciet gedetecteerd.
- Er is een API-route voor diagnose.
- Geen nieuwe frontend.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
