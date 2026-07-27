# Validatieplan — issue 196 backendrelease

## Technische controles

1. `python -m compileall backend/app/api/barcode_routes.py backend/app/services/generic_product_link_replacement_service.py`
2. `python backend/tests/test_barcode_household_article_link_service.py`
3. `python backend/tests/test_generic_product_link_replacement_service.py`
4. Backend health vóór en na regressie.
5. Controle dat frontendbestanden niet zijn gewijzigd.

## Runtimecontrole met kopie van productiegegevens

Gebruik uitsluitend een kopie van de actieve runtime-database. Controleer voor en na de vervanging:

- `household_articles.global_product_id`;
- aantal `inventory_events`;
- voorraadhoeveelheid;
- ruimte en sublocatie;
- artikelgroep;
- minimum- en ideale voorraad;
- notities;
- verwijzing van de bonregel naar hetzelfde huishoudartikel;
- bestaan van het oude generieke universele product.

## Stopcriteria

- een specifieke bestaande koppeling kan worden overschreven;
- mutatie zonder expliciete bevestiging;
- voorraad- of historiemutatie;
- huishoudisolatie faalt;
- frontendwijziging in deze backendrelease;
- build- of healthcheck niet groen.
