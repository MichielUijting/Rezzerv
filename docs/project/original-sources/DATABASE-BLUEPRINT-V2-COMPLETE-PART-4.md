# Volledige broninhoud — concrete v2 database blueprint voor Rezzerv, deel 4 van 4

Bronbestand: `concrete v2 database blueprint voor Rezzerv.docx`

  - global_products

  - product_identities

  - product_enrichments

  - product_enrichment_attempts

- GTIN/barcode wordt definitief primaire productsleutel

**Niet wijzigen**

- UI-layout

- inventory-events

- voorraadprojectie

- receipt parsing UX

**Datamigratie**

- voor bestaande verrijkingsdata:

  - koppel historische enrichmentrecords aan global_product_id

- laat huishoudspecifieke notities en voorkeuren buiten deze migratie

**Regressietest-scope**

- handmatig barcode invullen

- direct verrijken

- Open Food Facts found/not_found/failed

- bestaand verrijkt artikel opnieuw openen

- geen regressie in voorraad of artikeldetails

**Belang**

Dit is de release waarin de scheiding tussen **productkennis** en
**huishoudgebruik** echt definitief wordt.

**Release D — Artikeldetail-API verankeren op household_article**

**Categorie:** Breaking Change  
**Hoofddoel:** frontend stabiliseren op één functioneel anker

De huidige blueprint hangt artikeldetail nog aan
/api/articles/{articleId} en aan global_article_id als hoofdanker.  
Mijn advies blijft: maak household_article_id het functionele
hoofdanker.

**Wijzigen**

- nieuwe hoofdresource:

  - GET /api/household-articles/{id}

  - GET /api/household-articles/{id}/inventory

  - GET /api/household-articles/{id}/locations

  - GET /api/household-articles/{id}/events

  - GET /api/household-articles/{id}/product

- oude /api/articles/... routes tijdelijk adapteren of redirecten

**Niet wijzigen**

- zichtbare tabs

- bestaande UX

- voorraadtransactie

**Regressietest-scope**

- Overzicht

- Voorraad

- Locaties

- Historie

- Productverrijking

- barcode opslaan

- scannerflow

**Waarom apart**

Router/API-contractwijziging is volgens jullie protocol een breaking
change en moet dus niet gemengd worden met andere doelen.

**Release E — Receipt/importlaag naar productcatalogus brengen**

**Categorie:** Backend-release  
**Hoofddoel:** kassabonregels en importregels laten koppelen aan
global_products

**Wijzigen**

- receipt_lines.matched_global_product_id

- purchase_import_lines.household_article_id blijft

- matchinglogica eerst product, dan household_article

**Niet wijzigen**

- visuele kassabonflow

- uitpakken-flow

- voorraadprojectie

**Regressietest-scope**

- kassabon upload

- parsing naar tabel

- matching naar bestaand product

- toevoegen aan voorraad

- bestaande uitpakken-flow

**Belang**

Dit is nodig om van receipt naar productcatalogus te gaan zonder steeds
losse artikelkopieën te maken. Dit sluit direct aan op de visie dat
aankopen automatisch in Rezzerv verrijkt binnenkomen.

**Release F — Productmedia en documentlaag**

**Categorie:** Backend-release  
**Hoofddoel:** handleidingen, garantie en beelden kunnen opslaan op
productniveau

**Wijzigen**

- product_media

- product_documents

**Niet wijzigen**

- receiptflow

- voorraadflow

- detailroutering

**Regressietest-scope**

- bestaand product blijft zichtbaar

- detailpagina zonder media blijft werken

- enriched product met afbeelding/document kan worden getoond

**Waarom belangrijk**

Dit is direct in lijn met de Rezzerv-visie rond handleidingen en
garantie bij apparaten.

**Release G — Privacy- en serviceproviderlaag**

**Categorie:** Backend-release  
**Hoofddoel:** datadeling structureel modelleren

**Wijzigen**

- service_providers

- data_permissions

- service_subscriptions

- shared_data_exports

**Niet wijzigen**

- voorraad

- productverrijking

- barcode UX

**Regressietest-scope**

- bestaande huishoudfunctionaliteit

- bestaande productdetails

- geen onbedoelde datadeling

- permissies persistent

**Waarom belangrijk**

De Mosterd-visie zegt expliciet dat de gebruiker bepaalt wie welke data
krijgt. Dat hoort in een eigen datalaag, niet verspreid als losse
velden.

**Migratievolgorde in schema**

1.  **Release A** — nieuwe productcatalogustabellen

2.  **Release B** — household_articles koppelen aan global_products

3.  **Release C** — enrichment volledig productgericht

4.  **Release D** — API/route anker naar household_article

5.  **Release E** — receipt/import koppeling naar productcatalogus

6.  **Release F** — media/documenten

7.  **Release G** — privacy/serviceproviderlaag

**Wat bewust nog niet meenemen**

Deze zaken zou ik nog níet in dit migratiepad stoppen:

- analyse-tab logica

- AI-voorspellingen

- receptenmatching

- winkelvergelijking

- abonnementenbeheer

- uitleenfunctionaliteit

Die horen pas ná stabilisatie van productcatalogus + huishoudartikel +
voorraad + privacy.

**Belangrijkste beslisregels per release**

Voor elke release moet vooraf expliciet vastliggen:

- basisversie

- nieuwe versie

- releasecategorie

- exact wijzigingsdoel

- wat niet wordt gewijzigd

- impact op bestaande functionaliteit

- regressietest-scope
