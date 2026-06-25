# M2C2i-20a — Performancevalidatie Externe databases

## Doel

De Externe databases-tabel moet bij het bijlezen van een nieuwe pagina merkbaar sneller reageren, zonder functionele wijziging in kandidaatlogica.

## Wijziging

M2C2i-20a voegt lichte database-indexen toe rond de bestaande resolved-state flow:

- `external_product_candidates(context_key, updated_at)`
- `external_product_candidates(purchase_import_line_id, updated_at)`
- `external_product_candidates(receipt_line_id, updated_at)`
- `external_product_candidates(candidate_status, status, context_key)`

Daarnaast stopt de ensure-flow direct als de aangeleverde zichtbare items allemaal al resolved zijn. Dan wordt geen lege kandidaatzoekronde meer doorgezet.

## Opstartroutine

Gebruik bij lokale validatie altijd een wachttijd van 90 seconden na het starten of rebuilden van containers. Daarmee krijgen backend, frontend en database genoeg tijd om stabiel op te komen voordat de UI of smoke wordt getest.

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
git fetch origin
git switch m2c2i20a-external-db-pagination-performance
git pull --ff-only origin m2c2i20a-external-db-pagination-performance
docker compose up -d --build backend frontend
Start-Sleep -Seconds 90
```

## PO-test

1. Start lokaal volgens de opstartroutine hierboven.
2. Open `http://localhost:5174/externe-databases`.
3. Ga naar een volgende pagina in de tabel.
4. Herhaal dit een paar keer.
5. Controleer of het bijlezen merkbaar sneller en stabieler is.
6. Controleer dat bekende artikelen met externe artikelcode resolved blijven.
7. Controleer dat onbekende artikelen zonder externe artikelcode nog kandidaatzoekbaar blijven.

## Smoke zonder pytest

```powershell
@'
from app.services import external_database_matchflow_evidence as m

m._m2c2i20a_ensure_performance_indexes()

resolved = {
    "is_receipt_item_placeholder": True,
    "purchase_import_line_id": "pil-1",
    "receipt_line_text": "Veldsla",
    "retailer_code": "lidl",
    "retailer_article_number": "lidl:groente.veldsla",
}

result = m.ensure_external_receipt_item_candidates(items=[resolved], include_below_threshold=True)

assert result["processed"] == 0
assert result["external_resolved_skipped_count"] == 1
assert result["m2c2i20a_performance_indexes"] is True
assert result["creates_global_product"] is False
assert result["creates_household_article"] is False
assert result["creates_inventory_event"] is False

print("M2C2i-20a smoke OK: resolved-only refresh stopt direct en indexen zijn aanwezig.")
'@ | docker compose exec -T backend python
```

Verwacht:

```text
M2C2i-20a smoke OK: resolved-only refresh stopt direct en indexen zijn aanwezig.
```

## GO-criteria

- Nieuwe pagina in Externe databases laadt merkbaar sneller of in ieder geval niet trager.
- Artikelen met externe artikelcode blijven resolved.
- Onbekende artikelen blijven kandidaatzoekbaar.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
