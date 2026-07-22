# Volledige broninhoud — concrete v2 database blueprint voor Rezzerv, deel 3 van 4

Bronbestand: `concrete v2 database blueprint voor Rezzerv.docx`

  - events

  - product

- oude artikelroutes laten redirecten of adapteren

**Migratie 5 — privacy en services laag toevoegen**

**Doel:** visie structureel ondersteunen.

**Acties**

- service_providers

- data_permissions

- service_subscriptions

- shared_data_exports

**Migratie 6 — productmedia en documenten**

**Doel:** handleidingen, garantie en beelden kunnen dragen.

**Acties**

- product_media

- product_documents

**7. API-v2 richting**

De huidige blueprint gebruikt /api/articles/{articleId} als hoofdanker.
v2 moet dat stabiliseren naar household_article als functioneel
hoofdobject.

**Hoofdresource**

GET /api/household-articles/{id}  
GET /api/household-articles/{id}/inventory  
GET /api/household-articles/{id}/locations  
GET /api/household-articles/{id}/events  
GET /api/household-articles/{id}/product  
POST /api/household-articles/{id}/barcode  
POST /api/household-articles/{id}/enrich

**Productresource**

GET /api/products/{id}  
GET /api/products/{id}/enrichments  
GET /api/products/{id}/media  
GET /api/products/{id}/documents

**Inventory resource**

POST /api/inventory-events  
POST /api/inventory-transfers

**Receipt/import resource**

POST /api/receipts  
POST /api/receipts/{id}/parse  
POST /api/purchase-import-batches/{id}/sync

**8. Beslisregels voor data-opslag**

**Barcode**

- hoofdopslag op global_products.primary_gtin

- aanvullende opslag in product_identities

**Merk, titel, categorie, inhoud**

- op global_products

- enrichment mag deze bijwerken volgens bronprioriteit

**Ingrediënten, allergenen, nutrition, afbeeldingen**

- op product_enrichments

- laatste geslaagde enrichment per bron

**Huishoudnotities, minimumvoorraad, voorkeurwinkel**

- op household_articles

**Hoeveelheid en locatie**

- op inventory

**Aankoop/verbruik/transfer**

- op inventory_events

**9. Definitieve ontwerpkeuzes**

**Keuze 1**

**Één GTIN = één productrecord**

**Keuze 2**

**Huishouden gebruikt producten via household_articles**

**Keuze 3**

**Voorraad blijft projectie op events**

**Keuze 4**

**Productverrijking hoort bij product, niet bij inventory**

**Keuze 5**

**Receiptregels zijn importlaag, geen voorraadlaag**

**Keuze 6**

**Privacy en service-uitwisseling zijn aparte domeinlaag**

Dat alles is consistent met de bestaande Rezzerv-richting: database,
gebruiker, huishouden, bezittingen, artikelen, afnemers, leveranciers,
services en overzichten als afzonderlijke softwarecomponenten.

**10. Mijn eindadvies**

De **definitieve v2 database blueprint** voor Rezzerv is dus:

**Samenvatting**

- behoud de bestaande event-based voorraadbasis

- vervang global_articles functioneel door global_products

- laat household_articles naar die productcatalogus wijzen

- maak enrichment, identity, media en documenten centraal productgericht

- houd huishouddata en voorraaddata strikt apart

- voer de migraties gefaseerd uit

Dat is de veiligste route richting:

- Mijlpaal 2 stabieler maken

- productverrijking schaalbaar maken

- en de latere service- en privacylaag voorbereiden.

De volgende logische stap is dat ik dit omzet naar een **concreet
migratieplan per release**, met:

- basisversie

- nieuwe versie

- releasecategorie

- SQL per migratie

- impact

- regressietest-scope.

Hieronder staat het **concrete migratieplan per release** voor de
overgang naar het v2-datamodel.

Uitgangspunt:

- we bouwen voort op de huidige blueprint met global_articles,
  household_articles, inventory en inventory_events

- voorraad blijft **event-based**

- elke release heeft **exact één hoofddoel** en maximaal één
  releasecategorie

- geen release zonder Scope Gate, QA/QC Gate en Packaging Gate groen

Ik geef dit daarom als **voorstel voor een releasepad**, niet als
autonoom vastgestelde versienummers.

**Overzicht releasepad**

**Release A — Productcatalogusbasis**

**Categorie:** Infrastructuur Release  
**Hoofddoel:** centrale productcataloguslaag toevoegen zonder bestaande
flows om te breken

**Wijzigen**

- nieuwe tabel global_products

- nieuwe tabel product_identities

- nieuwe tabel product_enrichments

- nieuwe tabel product_enrichment_attempts

**Niet wijzigen**

- bestaande frontendroutes

- household_articles

- inventory

- inventory_events

- kassabonflow

- barcodeflow in UI

**Datamigratie**

- kopieer alle records uit global_articles naar global_products

- zet global_products.primary_gtin = global_articles.barcode

- voeg voor bestaande barcodes ook een product_identities record toe met
  type gtin

**Compatibiliteit**

- global_articles blijft voorlopig bestaan

- bestaande code mag nog op global_articles blijven lezen

- nieuwe enrichmentcode schrijft al naar global_products en product\_\*

**Regressietest-scope**

- login

- voorraadlijst

- artikeldetails openen

- kassabon → tabel → voorraad

- bestaande verrijkte artikelen moeten nog zichtbaar blijven

**Stopcriterium**

Als bestaande artikel-detailflow breekt, blokkeren. Nieuwe cataloguslaag
mag nooit zwaarder wegen dan werkende kernflow.

**Release B — Household-articles koppelen aan productcatalogus**

**Categorie:** Breaking Change  
**Hoofddoel:** household_articles laten verwijzen naar global_products

**Wijzigen**

- nieuwe kolom household_articles.global_product_id

- backfill vanuit oude household_articles.global_article_id

- nieuwe FK naar global_products

**Niet wijzigen**

- inventory

- inventory_events

- locatiestructuur

- barcode scan UI

**Datamigratie**

1.  kolom global_product_id nullable toevoegen

2.  vullen via mapping global_article_id -\> global_products.id

3.  constraint valideren

4.  oude kolom global_article_id nog tijdelijk laten staan als
    deprecated

**API-impact**

- backend mag intern al naar global_product_id overstappen

- frontend hoeft nog niet te veranderen

**Regressietest-scope**

- bestaande voorraadrecords per artikel

- detailpagina openen

- artikelnamen en merken blijven zichtbaar

- verrijkingsstatus blijft zichtbaar

- verbruik/aankoop-events blijven aan hetzelfde huishoudartikel hangen

**Architectuurrisico**

Dit is de eerste release waar de relationele kern echt verschuift.
Daarom apart uitvoeren. Dat volgt ook uit jullie integratiebeleid: per
release maximaal één infrastructuurwijziging of één backendfeature of
één UI-feature.

**Release C — Productverrijking volledig centraliseren**

**Categorie:** Backend-release  
**Hoofddoel:** enrichment niet meer per artikel-/detailflow, maar per
product

**Wijzigen**

- backend enrichmentservice leest en schrijft uitsluitend via:
