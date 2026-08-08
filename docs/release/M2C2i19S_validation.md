# M2C2i-19S — Validatie

## Doelvalidatie

Aantonen dat fallback-kandidaten niet meer worden gemaakt en dat alleen echte catalogus-/externe kandidaten zichtbaar worden.

## Opstartroutine

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
git fetch origin
git switch m2c2i19s-real-candidates-only
git pull --ff-only origin m2c2i19s-real-candidates-only
docker compose up -d --build backend frontend
Start-Sleep -Seconds 90
```

## Eerst oude fallback-data opschonen

```powershell
@'
from app.db import engine
from sqlalchemy import text

with engine.begin() as conn:
    deleted_candidates = conn.execute(text("""
        DELETE FROM external_product_candidates
        WHERE candidate_source_name IN ('receipt_product_intent_fallback', 'receipt_unresolved_fallback', 'learned_receipt_line')
           OR source_name IN ('receipt_product_intent_fallback', 'receipt_unresolved_fallback', 'learned_receipt_line')
           OR candidate_status IN ('fallback_candidate', 'unresolved_candidate', 'concept_candidate')
           OR candidate_source_product_code LIKE 'fallback:%'
           OR source_product_code LIKE 'fallback:%'
           OR created_by LIKE '%fallback%'
           OR created_by LIKE '%self_learning%'
    """)).rowcount

    deleted_index = conn.execute(text("""
        DELETE FROM external_product_index
        WHERE source_name = 'learned_receipt_line'
           OR source_product_code LIKE 'learned:%'
           OR code LIKE 'learned:%'
    """)).rowcount

print(f"Fallback cleanup OK: {deleted_candidates} candidates verwijderd, {deleted_index} indexregels verwijderd.")
'@ | docker compose exec -T backend python
```

## Smoke zonder pytest

```powershell
@'
from app.db import engine
from sqlalchemy import text
from app.services.external_database_matchflow_evidence import match_retailer_receipt_line

unknown = match_retailer_receipt_line('lidl', 'M2C2i19S onbekend geen echte match', include_below_threshold=True)
assert unknown['candidates'] == []
assert unknown.get('uses_coverage_fallback') is False
assert unknown.get('uses_legacy_fallback') is False
assert unknown.get('candidate_source') in {'no_real_candidate', 'external_product_index_no_match'}
assert unknown['creates_global_product'] is False
assert unknown['creates_household_article'] is False
assert unknown['creates_inventory_event'] is False

with engine.begin() as conn:
    leftovers = conn.execute(text("""
        SELECT COUNT(*) AS count
        FROM external_product_candidates
        WHERE candidate_source_name IN ('receipt_product_intent_fallback', 'receipt_unresolved_fallback', 'learned_receipt_line')
           OR source_name IN ('receipt_product_intent_fallback', 'receipt_unresolved_fallback', 'learned_receipt_line')
           OR candidate_status IN ('fallback_candidate', 'unresolved_candidate', 'concept_candidate')
           OR candidate_source_product_code LIKE 'fallback:%'
           OR source_product_code LIKE 'fallback:%'
    """)).mappings().first()['count']

assert int(leftovers) == 0

print('M2C2i-19S smoke OK: onbekende bonregel geeft geen fallback-kandidaat.')
'@ | docker compose exec -T backend python
```

Verwacht:

```text
M2C2i-19S smoke OK: onbekende bonregel geeft geen fallback-kandidaat.
```

## PO-test

1. Open `http://localhost:5174/externe-databases`.
2. Gebruik een onbekende Lidl-bonregel die geen echte match heeft.
3. Klik kandidaten bijlezen.
4. Controleer dat er geen fallback-/conceptkandidaat verschijnt.
5. Gebruik daarna een bonregel die wel in Lidl-catalogusverrijking zit.
6. Controleer dat alleen echte bronkandidaten verschijnen.

## GO-criteria

- Geen `receipt_product_intent_fallback`.
- Geen `receipt_unresolved_fallback`.
- Geen `learned_receipt_line`.
- Geen `concept_candidate`.
- Onbekend zonder echte bron blijft zonder kandidaat.
- Geen nieuwe frontend.
- Geen `global_products`-aanmaak.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
