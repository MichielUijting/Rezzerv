# Rezzerv Opstartroutine v1.13 - aanvulling ketentest

Deze aanvulling is een integraal en normatief onderdeel van `Rezzerv_Opstartroutine_v1.12.docx` voor wijzigingen die de keten Kassa, Uitpakken, Voorraad, Producttype, Spaartegoeden of Bijna op kunnen raken.

## 1. Wanneer verplicht uitvoeren

Voer de ketentest uit bij iedere wijziging aan een van de volgende onderdelen:

- kassabonimport of bonverwerking;
- Kassa;
- Uitpakken;
- universele artikelen en productidentiteiten;
- koppeling universeel artikel naar huishoudartikel;
- Producttype;
- inventory-events en voorraadprojectie;
- Voorraad;
- minimumvoorraad en Bijna op;
- herkenning of uitsluiting van spaar- en koopzegels.

Een rode ketentest betekent automatisch **NO-GO** voor merge of release.

## 2. Normatieve testcontext

- Testhuishouden: `0`.
- De test gebruikt een tijdelijke geisoleerde SQLite-runtime.
- Productiecode, productieschema en productieservices worden gebruikt.
- De normale runtime-database wordt niet gewijzigd.
- De ketentest mag geen handmatige voorraadaanpassing als vervanging voor de echte verwerking gebruiken.

## 3. Uitvoering

Voer vanuit de Rezzerv-projectmap uit:

```powershell
CLS
$ErrorActionPreference = "Stop"
cd C:\Users\Gebruiker\Rezzerv_Github

docker compose build backend
& ".\scripts\run-receipt-inventory-chain-v2.ps1" -SkipBackendBuild
```

## 4. Vereist groen bewijs

De uitvoering is alleen geldig wanneer beide markers voorkomen:

```text
RECEIPT_INVENTORY_ALMOST_OUT_CHAIN_GREEN
PRODUCT_TYPE_LINK_CONTRACT_GREEN
```

Daarna moet de afsluiting exact aantonen:

```text
KETENTEST GESLAAGD - 12/12 STAPPEN GROEN - 100%
Huishouden: 0
Voorraadpad: 0 -> 2 -> 5 -> 5 -> 1
Bijna-op-pad: NEE -> JA
Dubbele voorraadmutatie voorkomen: JA
Universeel product gekoppeld: JA
Producttype gekoppeld via productieservice: JA
Koopzegels buiten fysieke voorraad: JA
```

Een handmatig afgedrukte groene tekst na een eerdere fout is geen geldig testbewijs. Alleen de afsluiting van de runner zelf telt.

## 5. Vervolgcontrole voor merge

Na een groene ketentest:

1. voer de centrale frontendregressie uit;
2. verwijder tijdelijke Playwright-rapportmappen;
3. controleer dat `git status --short` leeg is;
4. leg het testbewijs vast in de PR;
5. merge uitsluitend na expliciete PO-GO.

De centrale frontendregressie blijft aanvullend en vervangt deze ketentest niet.

## 6. Huidige scope en begrenzing

De test bewijst op dit moment:

- echte Uitpakken-naar-Voorraadverwerking;
- voorraadpad `0 -> 2 -> 5 -> 5 -> 1`;
- idempotentie van purchase-events;
- koppeling van universeel product aan huishoudartikel;
- Producttypekoppeling via de productieservice;
- uitsluiting van koopzegels uit fysieke voorraad;
- Bijna-opovergang van niet opgenomen naar wel opgenomen.

Nog niet volledig gedekt zijn OCR van echte afbeeldingen, onbekende-artikelafhandeling, browsergestuurde end-to-endbediening en daadwerkelijke opslag/aggregatie van Spaartegoeden. Deze onderdelen blijven afzonderlijke vervolgreleases.