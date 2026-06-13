# M2C2f no-regression guardrails

## Guardrail 1 — geen automatische huishoudmutatie

De batch schrijft nooit zelfstandig naar `household_articles`.

## Guardrail 2 — geen voorraadmutatie

De batch bevat geen writes naar voorraadtabellen of voorraadbewegingen.

## Guardrail 3 — alleen bestaande relaties

Een apply is alleen geldig als kandidaat en huishoudartikel via hetzelfde `global_product_id` verbonden zijn.

## Guardrail 4 — idempotentie

Bij herhaalde apply wordt bestaande enrichment geactualiseerd in plaats van gedupliceerd.

## Guardrail 5 — expliciete adminbeslissing

Alle muterende acties verlopen via `POST /api/admin/external-relations/batch/decision`.
