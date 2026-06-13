# M2C2f admin API

## GET batch

```http
GET /api/admin/external-relations/batch
```

Retourneert batchbare kandidaat-huishoudartikelrelaties.

## POST decision

```http
POST /api/admin/external-relations/batch/decision
```

Voorbeelden:

```json
{"candidate_id":"...","decision":"later"}
```

```json
{"candidate_id":"...","household_article_id":"...","decision":"apply"}
```

```json
{"candidate_id":"...","household_article_id":"...","decision":"skip"}
```
