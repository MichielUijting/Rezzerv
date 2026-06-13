# M2C2f implementatienotities

De implementatie is backend-only om de datalaag eerst veilig te borgen.

## Tabellen

Nieuw:

- `external_relation_batch_decisions`

Bestaand en gebruikt:

- `external_product_candidates`
- `household_articles`
- `global_products`
- `product_enrichments`

## Waarom geen UI in deze stap?

De functionaliteit raakt huishoudadministratie. De eerste oplevering borgt daarom het contract en de guardrails via API-tests. Een UI kan daarna veilig bovenop deze endpoints worden geplaatst.
