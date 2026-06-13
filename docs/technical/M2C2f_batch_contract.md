# M2C2f batchcontract

## Input

De batch werkt alleen met bestaande records:

- `external_product_candidates.id`
- `external_product_candidates.global_product_id`
- `household_articles.id`
- `household_articles.global_product_id`

## Matchvoorwaarde

Een kandidaat is batchbaar als:

```text
external_product_candidates.global_product_id = household_articles.global_product_id
```

en beide waarden niet leeg zijn.

## Beslissingen

| Beslissing | Effect |
|---|---|
| `apply` | schrijft/actualiseert `product_enrichments` voor bestaand `household_article_id` |
| `skip` | legt auditbeslissing vast, geen enrichment |
| `later` | legt uitstel vast, geen enrichment |

## Guardrails

- Geen creatie van `household_articles`.
- Geen creatie van `global_products`.
- Geen voorraadmutatie.
- Geen verwerking zonder expliciete admin-beslissing.
