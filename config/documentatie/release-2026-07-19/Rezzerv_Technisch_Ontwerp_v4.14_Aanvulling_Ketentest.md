# Rezzerv Technisch Ontwerp v4.14 - aanvulling ketentest

Deze aanvulling is een integraal en normatief onderdeel van `Rezzerv-Technisch-Ontwerp-Volledig-Release-4_v4.13.docx`.

## 1. Doel

De ketentest beschermt de technisch risicovolle overgangen in de Rezzerv-keten:

```text
Kassabon / purchase import batch
-> geselecteerde importregel
-> universeel artikel
-> huishoudartikel
-> Uitpakken-verwerking
-> inventory-event
-> voorraadprojectie
-> Voorraad
-> Bijna op
```

Daarnaast wordt afzonderlijk bewezen dat een Producttype via de productieservice kan worden gekoppeld en dat koopzegels buiten de fysieke voorraadketen blijven.

## 2. Technische componenten

### 2.1 Hoofdketen

Bestand:

`backend/app/testing/receipt_inventory_production_chain.py`

De test:

- zet `DATABASE_URL` naar een tijdelijke SQLite-database;
- importeert de echte module `app.main`;
- initialiseert het bestaande productieschema;
- gebruikt huishouden `0`;
- roept de echte productiehandeling `process_purchase_import_batch` aan;
- controleert database-uitkomsten na iedere relevante overgang;
- verwijdert de tijdelijke database automatisch na afloop.

### 2.2 Producttypecontract

Bestand:

`backend/app/testing/product_type_link_contract.py`

De test:

- initialiseert expliciet het producttype- en productgroepschema;
- maakt een tijdelijk universeel product aan;
- roept `link_global_product_to_inventory_group` aan;
- controleert dat exact een actieve koppeling in `product_group_memberships` bestaat;
- gebruikt dus de productieservice en geen rechtstreeks gemanipuleerde einduitkomst.

### 2.3 Runner

Bestand:

`scripts/run-receipt-inventory-chain-v2.ps1`

De runner:

- valideert Docker Compose;
- kan de backend bouwen;
- voert beide Python-tests in tijdelijke backendcontainers uit;
- beoordeelt proces-exitcodes en inhoudelijke markers;
- geeft uitsluitend een groene eindmelding wanneer alle controles zijn geslaagd.

## 3. Normatieve verwachtingen

### 3.1 Voorraad en events

| Controle | Verwachting |
|---|---|
| Huishouden | `0` |
| Voorraadpad | `0 -> 2 -> 5 -> 5 -> 1` |
| Purchase-eventpad | `0 -> 1 -> 2 -> 2` |
| Dubbele verwerking | geen extra voorraad en geen extra purchase-event |
| Universele koppeling | exact een huishoudartikel voor het testproduct |

### 3.2 Producttype

| Controle | Verwachting |
|---|---|
| Productieservice | `link_global_product_to_inventory_group` |
| Actieve koppelingen | exact `1` |
| Opslagtabel | `product_group_memberships` |

### 3.3 Spaartegoeden en fysieke voorraad

- Een normale artikelregel wordt niet door de spaarzegeluitsluiting geraakt.
- Een koopzegelregel wordt wel uit de fysieke voorraadflow gehouden.
- Deze test bewijst nog niet de volledige opslag en aggregatie in `loyalty_stamp_transactions`.

### 3.4 Bijna op

- Minimumvoorraad van het testartikel: `2`.
- Bij voorraad `5`: niet opgenomen in Bijna op.
- Na consume-event naar voorraad `1`: wel opgenomen in Bijna op.
- De evaluatie gebruikt `evaluate_household_article_almost_out` en `build_almost_out_items` uit de productiecode.

## 4. Isolatie en veiligheid

De ketentest mag nooit afhankelijk zijn van bestaande gebruikersdata. De tijdelijke database moet:

- buiten de normale runtime-database staan;
- bij iedere uitvoering opnieuw worden opgebouwd;
- na afloop automatisch verdwijnen;
- hetzelfde schema en dezelfde services gebruiken als de backendproductiecode.

Testdata gebruikt herkenbare IDs met prefix `chain-` en uitsluitend huishouden `0` binnen de tijdelijke testdatabase.

## 5. Release-gate

De ketentest is verplicht bij wijzigingen aan:

- receipt parsing of purchase-import;
- Kassa en Uitpakken;
- productidentiteiten en universele artikelen;
- huishoudartikelen;
- Producttype;
- inventory en inventory-events;
- Voorraad en Bijna op;
- spaar- en koopzegelclassificatie.

Een fout in een van beide tests geeft automatisch **NO-GO**. De frontendregressie is een aanvullende gate en mag deze technische ketentest niet vervangen.

## 6. Huidige beperkingen en vervolgstappen

Nog toe te voegen in afzonderlijke testreleases:

1. echte OCR-afbeelding door de volledige keten;
2. onbekend artikel met expliciete koppeling in Uitpakken;
3. tweede huishouden voor aanvullende isolatiecontrole;
4. echte opslag en aggregatie van Spaartegoeden;
5. browsergestuurde Kassa -> Uitpakken -> Voorraad -> Bijna-optest;
6. transactionele foutinjectie en retrycontrole.

De huidige test vormt daarmee de normatieve backend-golden-path, maar nog niet de volledige uiteindelijke end-to-enddekking.