# M2C2f — Batchfunctie externe relaties doorvoeren naar huishoudadministratie

## Doel

Deze stap voegt een veilige admin-backendbatch toe waarmee externe productrelaties gecontroleerd kunnen worden doorgevoerd naar bestaande huishoudartikelen.

## Uitgangspunten

- `external_product_candidates` bevat externe kandidaten.
- Alleen kandidaten met een bestaand `global_product_id` komen in aanmerking.
- Alleen bestaande `household_articles` met hetzelfde `global_product_id` komen in aanmerking.
- De admin kiest expliciet `apply`, `skip` of `later`.
- De batch maakt geen nieuwe `household_articles` aan.
- De batch maakt geen voorraadmutaties.
- `product_enrichments` wordt alleen geschreven bij `apply` en altijd met een bestaande `household_article_id`.

## Endpoints

### Lijst batchitems

```http
GET /api/admin/external-relations/batch?limit=50
```

Optioneel:

```http
GET /api/admin/external-relations/batch?household_id=<id>&limit=50
```

### Beslissing vastleggen

```http
POST /api/admin/external-relations/batch/decision
```

Body:

```json
{
  "candidate_id": "...",
  "household_article_id": "...",
  "decision": "apply",
  "decision_reason": "PO-test"
}
```

Toegestane beslissingen:

- `apply`
- `skip`
- `later`

## Verwachte negatieve test op huidige dataset

Omdat de huidige M2C2e-testkandidaat nog geen `global_product_id` heeft, hoort de batchlijst leeg te blijven:

```powershell
Invoke-RestMethod "http://localhost:8011/api/admin/external-relations/batch?limit=50"
```

Verwachting:

```text
items: []
```

Controle dat er geen ongewenste records bijkomen:

```powershell
@'
import sqlite3
conn = sqlite3.connect("/app/data/rezzerv.db")
for table in ["household_articles", "product_enrichments", "external_relation_batch_decisions"]:
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(table, count)
    except Exception as exc:
        print(table, "ERROR", exc)
'@ | docker compose exec -T backend python -
```

Verwachting:

- `household_articles` blijft gelijk.
- `product_enrichments` blijft gelijk zolang geen apply mogelijk is.
- `external_relation_batch_decisions` bestaat en bevat alleen expliciete admin-keuzes.
