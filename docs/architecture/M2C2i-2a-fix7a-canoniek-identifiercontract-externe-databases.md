# M2C2i-2a-fix7a — Canoniek identifiercontract Externe databases

## Doel

Het functiegebied Externe databases gebruikt geen extra nieuwe id-laag om bestaande verwarring te verhullen. Bestaande technische velden blijven bestaan voor herkomst en migratie, maar de API levert één canoniek contract aan de frontend.

## Architectuurprincipe

Niet telkens iets nieuws toevoegen. Eerst hergebruik en canonisatie van bestaande onderdelen.

## Canonieke velden in het Externe-databases-contract

| Canoniek veld | Betekenis | Afgeleid uit bestaande velden |
|---|---|---|
| `context_key` | De enige UI/API-sleutel voor één bonartikelcontext | bestaande `context_key`; anders bestaande receipt/purchase id-logica |
| `candidate_id` | De kandidaatregel binnen de context | bestaande `id` van `external_product_candidates` |
| `external_source_name` | Externe bron | `candidate_source_name`, anders `source_name` |
| `external_source_product_code` | Artikelcode bij de externe bron | `candidate_source_product_code`, anders `source_product_code`, anders `retailer_article_number` |
| `gtin` | Barcode indien beschikbaar | bestaande `gtin`, `ean` of `code` |
| `canonical_catalog_product_id` | Enige logische catalogusreferentie voor Externe databases | `global_product_id`, `matched_global_product_id`, `matched_global_article_id`, `product_identity_id` |
| `is_linked_to_catalog` | Enige UI-statusbron voor gekoppeld/niet gekoppeld | backend-normalisatie |
| `is_linkable_to_catalog` | Enige UI-statusbron voor koppelbaar | backend-normalisatie |
| `status_label` | Gebruikerslabel | backend-normalisatie |

## Niet-canonieke velden

Deze velden mogen technisch blijven bestaan, maar zijn geen frontendbeslissingsvelden meer:

- `global_product_id`
- `matched_global_product_id`
- `matched_global_article_id`
- `product_identity_id`
- `candidate_status`
- `status`
- `is_user_confirmed`
- `is_external_database_override`
- `receipt_line_id`
- `purchase_import_line_id`

## Acceptatiecriteria

1. De backendresponse bevat de canonieke velden.
2. De frontend gebruikt voor Externe databases de canonieke contractvelden waar mogelijk.
3. Er worden geen nieuwe concurrerende id-velden toegevoegd.
4. Bestaande technische velden blijven beschikbaar zolang de backend ze nodig heeft.
5. Fix7b mag pas daarna bepalen of artikelcode + catalogusgegevens als gekoppeld telt.
