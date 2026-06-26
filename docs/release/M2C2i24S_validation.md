# M2C2i-24S — Validatie

## Doelvalidatie

M2C2i-24S valideert blind of nieuwe bonartikelen generiek door de externe-herkenningsstraat lopen.

De test mag niet vooraf weten welke artikelnamen worden getest.

M2C2i-24S-a voegt productgedrag toe: na het opslaan van nieuwe bonartikelen wordt de herkenning automatisch aangeroepen.

## Rebuild

```powershell
docker compose up -d --build backend frontend
Start-Sleep -Seconds 90
```

## Smoke via backend-Python

```powershell
@'
from app.services.external_receipt_coverage_report import build_blind_receipt_coverage_report

result = build_blind_receipt_coverage_report(limit=500, include_below_threshold=True)

assert result['ok'] is True
assert result['mode'] == 'blind_receipt_item_coverage'
assert result['creates_global_product'] is False
assert result['creates_household_article'] is False
assert result['creates_inventory_event'] is False
assert result['writes_database'] is False
assert result['forbidden_candidate_count'] == 0
assert result['coverage_fallback_item_count'] == 0
assert result['legacy_fallback_item_count'] == 0

assert result['total_items'] >= 1
assert len(result['items']) == result['total_items']

for item in result['items']:
    assert item['receipt_line_text']
    assert item['forbidden_candidate_count'] == 0
    assert item['uses_coverage_fallback'] is False
    assert item['uses_legacy_fallback'] is False

print('M2C2i-24S smoke OK: blind coverage-scan verwerkt alle actuele bonartikelen veilig.')
print('total_items:', result['total_items'])
print('items_with_real_candidate:', result['items_with_real_candidate'])
print('items_without_real_candidate:', result['items_without_real_candidate'])
'@ | docker compose exec -T backend python
```

## Smoke M2C2i-24S-a — hook

```powershell
@'
from app.services.external_receipt_auto_coverage import install_receipt_auto_candidate_coverage

result = install_receipt_auto_candidate_coverage()
assert result['ok'] is True
assert result['creates_global_product'] is False
assert result['creates_household_article'] is False
assert result['creates_inventory_event'] is False
print('M2C2i-24S-a hook OK:', result['patched'])
'@ | docker compose exec -T backend python
```

## API-validatie

```powershell
$body = @{ limit = 500; include_below_threshold = $true } | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8011/api/external-databases/coverage/receipt-items" `
  -ContentType "application/json" `
  -Body $body
```

## PO-acceptatie

Akkoord wanneer:

```text
- total_items >= aantal actuele bonartikelen binnen limiet
- items_with_forbidden_fallback = 0
- forbidden_candidate_count = 0
- coverage_fallback_item_count = 0
- legacy_fallback_item_count = 0
- bonregels met brondata tonen echte kandidaat
- bonregels zonder brondata tonen veilig geen echte bronmatch
- automatische hook is geïnstalleerd bij startup
- nieuwe bonnen krijgen external_candidate_coverage in de ingest response
- kandidaatcache in external_product_candidates mag worden gevuld
- geen Mijn-artikel
- geen global product
- geen voorraadmutatie
```
