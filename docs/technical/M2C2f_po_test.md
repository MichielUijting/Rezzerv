# PO-test M2C2f

## Voorbereiding

Gebruik de branch:

```powershell
git fetch origin
git switch feature/externe-relaties-household-batch
git pull --ff-only origin feature/externe-relaties-household-batch

docker compose down
docker compose up -d --build
Start-Sleep -Seconds 90
Invoke-RestMethod http://localhost:8011/api/health
```

## Test 1 — Batchlijst op huidige dataset

```powershell
Invoke-RestMethod "http://localhost:8011/api/admin/external-relations/batch?limit=50"
```

Verwachting:

```text
items: []
```

Dit is correct zolang geen kandidaat met `global_product_id` bestaat die matcht met een bestaand huishoudartikel.

## Test 2 — Audit-tabel bestaat zonder ongewenste mutaties

```powershell
@'
import sqlite3
conn = sqlite3.connect("/app/data/rezzerv.db")
for table in ["household_articles", "global_products", "product_enrichments", "external_relation_batch_decisions"]:
    try:
        print(table, conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception as exc:
        print(table, "ERROR", exc)
'@ | docker compose exec -T backend python -
```

Verwachting op huidige dataset:

- `household_articles` blijft 5.
- `global_products` blijft 9.
- `product_enrichments` blijft 0 zolang geen apply is gedaan.
- `external_relation_batch_decisions` bestaat.

## Test 3 — Later-beslissing zonder huishoudartikel

```powershell
$body = @{ candidate_id = "6ddfd5a8-9be4-44a8-a6c7-c5ed086955ab"; decision = "later"; decision_reason = "PO-test" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8011/api/admin/external-relations/batch/decision" -ContentType "application/json" -Body $body
```

Verwachting:

```text
ok: true
applied: false
decision: later
creates_household_article: false
creates_inventory_event: false
```

## Acceptatie

M2C2f is akkoord als:

- de batchlijst veilig leeg kan zijn;
- `later` veilig wordt vastgelegd;
- er geen household/global/inventory records ontstaan;
- apply alleen mogelijk is met bestaande kandidaat + bestaand household_article met dezelfde `global_product_id`.
