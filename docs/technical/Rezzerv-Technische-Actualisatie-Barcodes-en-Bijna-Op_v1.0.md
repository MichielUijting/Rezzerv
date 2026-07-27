# Rezzerv – Technische actualisatie barcodes en Bijna op

**Versie:** 1.0  
**Datum:** 27 juli 2026  
**Status:** actuele technische referentie voor de featurebranch  
**Branch:** `feature/external-databases-barcode-input`

## 1. Scope

Dit document beschrijft de gerealiseerde technische wijzigingen voor:

1. barcode-invoer en scanning op meerdere plaatsen in de frontend;
2. centrale barcodevalidatie en productlookup;
3. koppeling van bonartikelen aan globale producten en Producttypen;
4. serverpaginering en read-only uitlezing van bonartikelen;
5. Producttype-gebaseerde Bijna-op-berekening;
6. Producttype-instellingen per huishouden;
7. read-only migratieanalyse van huishoudartikelinstellingen.

Het document maakt onderscheid tussen gerealiseerde backendfundamenten en nog niet geactiveerde gebruikersfunctionaliteit.

---

## 2. Barcodecomponenten en frontendworkflow

### 2.1 Gedeelde componenten

De barcodefunctionaliteit gebruikt gedeelde frontendonderdelen voor:

- handmatige invoer;
- camerascanning;
- normalisatie;
- formaatvalidatie;
- lookup;
- status- en foutfeedback.

Belangrijke componenten en modules:

- `frontend/src/lib/useBarcodeScanner.js`
- `frontend/src/features/barcodes/BarcodeIdentityField.jsx`
- `frontend/src/features/barcodes/BarcodeScannerModal.jsx`
- `frontend/src/features/barcodes/barcodeReceiptWorkflow.js`

Hierdoor gelden dezelfde basisregels voor handmatige invoer en camera-invoer.

### 2.2 Artikeldetail

De barcodeworkflow is opgenomen in Artikeldetail via de product-/externe-koppelkaart.

Belangrijke module:

- `frontend/src/features/articles/tabs/ArticleOverviewTab.jsx`

De workflow:

1. bepaalt of camerascanning op het apparaat bruikbaar is;
2. normaliseert de gescande waarde;
3. vult het barcodeveld;
4. slaat de externe productidentiteit op;
5. vernieuwt de artikeldetails;
6. kan directe productverrijking starten;
7. vereist bevestiging bij overschrijven van een bestaande koppeling.

### 2.3 Externe databases – bonartikelen

Belangrijke modules:

- `frontend/src/features/externalDatabases/ExternalDatabasesPage.jsx`
- `frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx`

`ReceiptItemsOverview` gebruikt de gedeelde scanner en barcodecomponenten. De hoofdtabel behandelt een barcode als universele code wanneer deze overeenkomt met GTIN/EAN-lengtes 8, 12, 13 of 14.

Retailer- en seedcodes worden technisch onderscheiden van universele codes. Niet-universele codes mogen zoekhulp zijn, maar vormen geen definitieve catalogusidentiteit.

---

## 3. Barcodecontract en mutatiegrenzen

### 3.1 Productidentiteit

Een barcodekoppeling kan leiden tot:

- lookup in externe productbronnen;
- hergebruik of creatie van een globaal product volgens het bestaande productcontract;
- vastlegging van een primaire productidentiteit;
- koppeling van het globale product aan een bevestigd Producttype.

### 3.2 Atomair gedrag

De bestaande contracttests borgen onder meer:

- kandidaatsopslag en Producttypekoppeling als gecontroleerde transactie;
- OFF-resultaat en Producttypekoppeling als gecontroleerde transactie;
- rollback bij een mislukte koppeling;
- geen ongewenste opslag van kandidaat of voorraad bij een falend contract.

### 3.3 Read-only GET

De uitleesroute voor bonartikelen is read-only. Reparatie- of normalisatieacties zijn afgescheiden naar expliciete schrijfroutes.

Technische regel:

> Een GET-route mag geen schema-, kandidaat-, catalogus-, koppeling- of voorraadmutatie uitvoeren.

---

## 4. Serverpaginering bonartikelen

De bonartikelenservice ondersteunt serverpaginering met zichtbare regels als paginatiegrondslag.

Contracteigenschappen:

- vaste paginagrootte vanuit de frontend;
- servermetadata voor totaal, pagina en pagina-aantal;
- projectiemodus `visible_page_only`;
- niet-zichtbare of uitgesloten regels vullen de pagina niet kunstmatig;
- filters behouden correcte paginatiemetadata;
- frontendmocks en regressietests volgen het paginatiecontract.

De frontend gebruikt momenteel `PAGE_SIZE = 10` in `ReceiptItemsOverview.jsx`.

---

## 5. Producttypegegevensmodel

### 5.1 Bestaande Producttypelaag

Relevante tabellen:

- `product_inventory_groups`
- `product_group_memberships`
- `product_unit_conversions`
- `inventory_item_group_assignments`

Belangrijke regels:

- één actief Producttype per globaal product;
- actieve officiële GS1 GPC Producttypen zijn leidend voor Bijna op;
- een voorraadregel kan rechtstreeks aan een Producttype gekoppeld zijn;
- anders wordt de Producttypekoppeling via productidentiteit en globaal product gevonden;
- eenheidsconversies zijn product- en eventueel Producttypegebonden.

### 5.2 Producttype-instellingen per huishouden

Nieuwe tabel:

`household_product_type_settings`

Primaire sleutel:

`(household_id, product_type_id)`

Velden:

- `household_id`
- `product_type_id`
- `min_stock`
- `ideal_stock`
- `consumable`
- `active`
- `favorite_store`
- `average_price`
- `status`
- `default_location_id`
- `default_sublocation_id`
- `auto_restock`
- `packaging_unit`
- `packaging_quantity`
- `notes`
- `created_at`
- `updated_at`

Schema-uitbreiding is idempotent. Ontbrekende uitgebreide kolommen worden toegevoegd zonder bestaande instellingen te verwijderen.

Belangrijke modules:

- `backend/app/services/product_type_almost_out_service.py`
- `backend/app/services/product_type_household_settings_service.py`

---

## 6. Validatie Producttype-instellingen

De services valideren:

- huishouden en Producttype zijn aanwezig;
- Producttype is actief;
- Producttype is een officiële GS1 GPC-koppeling;
- minimum en streef zijn niet negatief;
- streef is niet lager dan minimum;
- prijsindicatie is niet negatief;
- verpakkingshoeveelheid is niet negatief;
- een positieve verpakkingshoeveelheid vereist een verpakkingseenheid;
- status is `active` of `inactive`;
- standaardruimte is actief en behoort tot het huishouden;
- standaardsublocatie behoort tot de gekozen ruimte en het huishouden.

De uitgebreide upsert schrijft alle huishoudspecifieke Producttype-instellingen in één transactie.

---

## 7. API-routes Producttype-Bijna-op

### 7.1 Instellingen opvragen

`GET /api/households/{household_id}/product-type-almost-out/settings`

Retourneert de Producttype-instellingen van het huishouden, inclusief Producttypenaam, basiseenheid en aggregatiemodus.

### 7.2 Instelling opslaan

`PUT /api/households/{household_id}/product-type-almost-out/settings/{product_type_id}`

Slaat het uitgebreide huishoudspecifieke instellingencontract op.

Dit is een expliciete schrijfroute.

### 7.3 Read-only preview

`GET /api/households/{household_id}/product-type-almost-out/preview`

Retourneert:

- `basis = product_type`;
- `read_only = true`;
- alle beoordeelde Producttypen;
- de Producttypen die volgens de berekening Bijna op zijn;
- blokkades en ontbrekende conversiegegevens waar van toepassing.

### 7.4 Read-only migratieanalyse

`GET /api/households/{household_id}/product-type-almost-out/migration-analysis`

Retourneert bestaande huishoudartikelinstellingen gegroepeerd per bevestigd Producttype.

De route schrijft niets.

---

## 8. Producttype-Bijna-op-berekening

### 8.1 Bronselectie

De service leest actieve voorraadregels binnen het huishouden en bepaalt per regel het Producttype via:

1. directe `inventory_item_group_assignments`; of
2. `product_identities` naar `global_product_id`; en
3. `product_group_memberships` naar `inventory_group_key`.

### 8.2 Hoeveelheidsconversie

De service gebruikt `product_unit_conversions` en converteert naar de basiseenheid van het Producttype.

Ondersteunde dimensies in het huidige contract:

- massa: mg, g, kg;
- volume: ml, cl, dl, l/liter/litre;
- aantallen: stuk/stuks, piece/pieces, rol/rollen, wasbeurt/wasbeurten.

Bij ontbrekende identiteit, ontbrekende conversie of incompatibele eenheid wordt de regel niet stilzwijgend als correcte hoeveelheid meegerekend.

### 8.3 Aggregatie

Per Producttype worden opgeteld:

- alle converteerbare actieve voorraadregels;
- alle locaties en sublocaties;
- alle merken en globale producten binnen hetzelfde Producttype.

De uitkomst bevat onder meer:

- Producttype-ID en naam;
- basiseenheid;
- actuele hoeveelheid;
- minimum en streef;
- te kopen hoeveelheid;
- include-in-almost-out;
- reden en datastatus;
- aantal bijdragende artikelen en voorraadregels.

### 8.4 Oude artikelgrenzen

`household_article.min_stock`, `household_article.ideal_stock` en artikelgerichte settings zijn geen beslissende bron voor de nieuwe Producttypepreview.

Deze gegevens worden alleen nog gebruikt als bron voor de read-only migratieanalyse totdat de gecontroleerde migratie is uitgevoerd.

---

## 9. Migratieanalyse

Belangrijke module:

- `backend/app/services/product_type_household_settings_service.py`

De analyse leest:

- `household_articles`;
- `household_article_settings`;
- `product_identities`;
- `product_group_memberships`;
- `product_inventory_groups`.

Per migreerbaar veld wordt een resolutie gemaakt:

- `missing`;
- `ready`;
- `conflict`.

Wanneer minimum of streef beschikbaar is maar geen bruikbare verpakkingsinformatie, wordt `review_required` gebruikt.

Migreerbare velden:

- `min_stock`
- `ideal_stock`
- `favorite_store`
- `average_price`
- `status`
- `default_location_id`
- `default_sublocation_id`
- `auto_restock`
- `packaging_unit`
- `packaging_quantity`
- `notes`

De deduplicatie waarborgt dat ieder huishoudartikel maximaal één keer voorkomt in:

- `unmapped_articles`; en
- een Producttypebucket.

---

## 10. Tests en bewezen status

Bewezen groene contracten:

### Barcode en Producttypekoppeling

- `PRODUCT_TYPE_LINK_CONTRACT_GREEN`
- `OFF_PRODUCT_TYPE_LINK_CONTRACT_GREEN`

### Producttype-Bijna-op Fase A/B

- `PASS product_type_settings_contract`
- `PASS product_type_multi_article_aggregation`
- `PASS product_type_unit_conversion`
- `PASS legacy_article_thresholds_ignored`
- `PRODUCT_TYPE_ALMOST_OUT_PHASE_AB_GREEN`

### Producttype-instellingen en migratie C1/C2

- `PASS product_type_extended_settings_schema`
- `PASS product_type_extended_settings_roundtrip`
- `PASS product_type_extended_settings_list`
- `PASS product_type_extended_settings_validation`
- `PASS product_type_migration_analysis_read_only`
- `PRODUCT_TYPE_ALMOST_OUT_PHASE_C1_C2_GREEN`

### Migratiededuplicatie

- `PRODUCT_TYPE_MIGRATION_UNIQUE_ARTICLES_CONFIRMED`

### Frontendregressie vóór de Bijna-op-documentatieactualisatie

- 26 Playwright-tests geslaagd;
- `REGRESSION_AND_CHAIN_GREEN`.

---

## 11. Actuele datastatus huishouden 1

De laatste read-only migratieanalyse gaf:

- 0 Producttypen met migreerbare instellingen;
- 10 unieke actieve huishoudartikelen zonder bruikbare bevestigde Producttypekoppeling;
- geen mutaties door de analyse.

Dit is geen fout in het migratiecontract. Het betekent dat de brongegevens eerst Producttypekoppelingen nodig hebben voordat migratievoorstellen kunnen ontstaan.

---

## 12. Nog openstaande technische stappen

1. UI voor Producttype-instellingen realiseren.
2. UI voor migratievoorstellen en conflictafhandeling realiseren.
3. Huidige huishoudartikelen gecontroleerd aan globale producten en Producttypen koppelen.
4. Expliciete migratieschrijfroute ontwerpen en testen.
5. Producttype-Bijna-op als actieve bron voor het zichtbare scherm inschakelen.
6. Producttype-gebaseerde voorspelling aansluiten op aankoop- en verbruikshistorie.
7. Producttypebehoefte aansluiten op de inkooplijst.
8. Oude artikelgerichte Bijna-op-logica pas na acceptatie uitschakelen.

---

## 13. Release- en regressieregels

- Geen merge naar `main` zonder expliciete Product Owner-autorisatie.
- GET-routes blijven mutatievrij.
- Bestaande barcode-, catalogus-, OFF-, voorraad- en kassabonketens moeten regressievrij blijven.
- De definitieve omschakeling van Bijna op vereist functionele acceptatie van de Producttype-instellingen en migratie.
- Oude instellingen blijven beschikbaar voor audit en terugval totdat de omschakeling definitief is geaccepteerd.
