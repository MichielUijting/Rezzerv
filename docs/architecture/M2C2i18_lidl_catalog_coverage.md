# M2C2i-18 — Lidl catalogusdekking uitbreiden

## Doel

Meer zichtbare Lidl-bonartikelen krijgen een externe productkandidaat zonder Python-productlogica toe te voegen.

## Scope

- Uitbreiding van `backend/app/data/lidl_catalog_enrichment_seed.json`.
- Configuratie/data-release voor Lidl-dekking.
- Geen UI-wijziging.
- Geen voorraadmutatie.
- Geen automatische definitieve productkoppeling.

## Aanpak

De toegevoegde regels bevatten per bontekst:

- `receipt_terms`
- `source_product_code`
- `catalog_product_name`
- `brand`
- `category`
- `product_type`
- `quantity_label`
- `confidence`
- `search_terms`

## Acceptatie

- Zichtbare Lidl-bonartikelen uit de PO-screenshots hebben vaker een kandidaat/code.
- Safety flags blijven false.
- Productkennis staat alleen in JSON/configuratie.
