# M2C2i-24S — Validatie

M2C2i-24S valideert blind of nieuwe bonartikelen generiek door de herkenningsstraat lopen.

M2C2i-24S-a voegt productgedrag toe: na het opslaan van nieuwe bonartikelen wordt de herkenning automatisch aangeroepen.

## Rebuild

```powershell
docker compose up -d --build backend frontend
Start-Sleep -Seconds 90
```

## Smoke blind rapport

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
print('M2C2i-24S smoke OK')
print('total_items:', result['total_items'])
print('items_with_real_candidate:', result['items_with_real_candidate'])
print('items_without_real_candidate:', result['items_without_real_candidate'])
'@ | docker compose exec -T backend python
```

## Smoke startup-hook

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

## Smoke bestaande bon

```powershell
@'
from sqlalchemy import text
from app.db import engine
from app.services.external_receipt_auto_coverage import auto_ensure_external_candidates_for_receipt_table
with engine.begin() as conn:
    row = conn.execute(text('SELECT id FROM receipt_tables ORDER BY created_at DESC, id DESC LIMIT 1')).mappings().first()
assert row, 'Geen receipt_table gevonden'
result = auto_ensure_external_candidates_for_receipt_table(str(row['id']))
assert result['ok'] is True
assert result['creates_global_product'] is False
assert result['creates_household_article'] is False
assert result['creates_inventory_event'] is False
print('M2C2i-24S-a service OK:', result)
'@ | docker compose exec -T backend python
```

## PO-acceptatie

```text
- blind rapport blijft veilig
- startup-hook is actief
- nieuwe bonnen krijgen external_candidate_coverage in de ingest response
- kandidaatcache mag worden gevuld
- geen Mijn-artikel
- geen global product
- geen voorraadmutatie
```
