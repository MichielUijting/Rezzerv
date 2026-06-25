# M2C2i-17 — Dynamische retailer-aliaslearning

## Doel

Nieuwe bontekstvarianten moeten dezelfde externe productkandidaat kunnen krijgen als een eerder betrouwbaar herkende bonregel, zonder dat productkennis in Python-code wordt vastgelegd.

## Besluit

Rezzerv leert alleen externe kandidaat-herkenning:

- geen `global_products` aanmaken
- geen huishoudartikel aanmaken
- geen voorraadmutatie aanmaken

## Implementatie

- Nieuwe tabel: `external_product_aliases`
- Nieuwe service: `backend/app/services/external_product_alias_store.py`
- Matchflow gebruikt aliaskandidaten naast de bestaande index-, catalogus- en taxonomy-kandidaten.
- Bij score >= 0.90 en een bruikbare externe code wordt de bontekst als alias opgeslagen.
- Canonieke seedregels worden als aliasbasis ingelezen vanuit `lidl_catalog_enrichment_seed.json`.

## Acceptatie

- Een betrouwbare match wordt als alias opgeslagen.
- Een latere bontekstvariant kan via de aliaslaag opnieuw dezelfde kandidaat tonen.
- Safety flags blijven false.
- Productkennis blijft in JSON/data of database, niet in Python-code.
