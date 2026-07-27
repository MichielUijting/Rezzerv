# Issue 196 — backendcontract veilige vervanging generieke productkoppeling

## Releasecategorie
Backend-release

## Hoofddoel
Een bestaand generiek universeel product zonder GTIN kan uitsluitend na expliciete bevestiging worden vervangen door een volledig en eenduidig herkend universeel product.

## Endpoint

`POST /api/barcodes/{gtin}/replace-generic-household-article-link`

Payload:

```json
{
  "purchase_import_line_id": "...",
  "household_article_id": "...",
  "global_product_id": "...",
  "confirm_replace_generic_link": false
}
```

Zonder bevestiging retourneert de backend HTTP 409 met code `REPLACEMENT_CONFIRMATION_REQUIRED`, inclusief het huidige en het geselecteerde universele product.

Met `confirm_replace_generic_link: true` wordt alleen `household_articles.global_product_id` vervangen. De bestaande bonregel blijft naar hetzelfde huishoudartikel verwijzen.

## Veiligheidsregels

- Alleen een actief handmatig product zonder primaire GTIN en zonder GTIN/EAN/UPC-identiteit geldt als vervangbaar generiek product.
- Een specifieke bestaande koppeling blijft geblokkeerd met `GENERIC_REPLACEMENT_BLOCKED`.
- Het oude universele product wordt niet verwijderd.
- Er wordt geen nieuw huishoudartikel gemaakt.
- Voorraad, locatie, sublocatie, artikelgroep, minimumvoorraad, ideale voorraad en notities blijven behouden.
- Het aantal `inventory_events` moet voor en na de actie gelijk zijn.
- Huishoudisolatie wordt opnieuw gecontroleerd binnen dezelfde databasetransactie.

## Backendcontracttest

`backend/tests/test_generic_product_link_replacement_service.py`

Dekt af:

1. bevestiging vereist zonder mutatie;
2. bevestigde vervanging met behoud van huishoud- en voorraaddata;
3. bescherming van een specifieke bestaande koppeling;
4. huishoudisolatie.

## Niet gewijzigd

- frontend;
- voorraadberekening;
- kassabonparser;
- locatiestructuur;
- artikelgroepen;
- algemene GPC-classificatielogica.
