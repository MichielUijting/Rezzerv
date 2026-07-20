# Rezzerv-Werkinstructies AI v9

Deze werkinstructie is verplicht voor alle Rezzerv-code-, validatie-, Git-, Docker-, PowerShell- en PR-acties.

## 1. Doel

Deze instructie voorkomt dat Rezzerv-werk wordt uitgevoerd op basis van aannames, geïmproviseerde scripts, onveilige PowerShell-blokken of onvolledige validatie.

De hoofdregel is:

> Eerst actuele context ophalen, dan oorzaak vaststellen, dan minimale wijziging, daarna vaste validatie.

## 2. Rezzerv Gatecheck

Voor iedere Rezzerv-actie moet deze poort worden doorlopen.

```text
REZZERV GATECHECK

1. Is dit een Rezzerv-code-, validatie-, Git-, Docker-, PowerShell- of PR-actie?
2. Is eerst actuele context opgehaald?
3. Gebruik ik geen verboden constructies?
   - geen here-string
   - geen lange kwetsbare PowerShell-patch
   - geen willekeurige sleep
   - geen lokale npm-route als primaire validatie
   - geen aanname over branch/runtime/browserbundle
4. Begint elk PowerShell-blok met:
   CLS
   $ErrorActionPreference = "Stop"
   cd C:\Users\Gebruiker\Rezzerv_Github
5. Is de stap minimaal en controleerbaar?
6. Is de validatie volgens het vaste protocol?
7. Blijft de PR draft totdat PO-check en regressie akkoord zijn?
```

Als één punt niet akkoord is, mag de stap niet worden uitgevoerd.

## 3. Verboden werkwijzen

### 3.1 Geen geïmproviseerde scripts

Verboden:

- Lange PowerShell-blokken met kwetsbare inline tekstvervanging.
- Here-strings zoals `@' ... '@` of `@" ... "@`.
- Scripts die de gebruiker in een secondary prompt `>>` kunnen laten belanden.
- Patches op basis van aannames over exacte tekstankers.

Maatregel:

- Eerst actuele context ophalen.
- Dan korte, controleerbare stappen.
- Bij codewijzigingen bij voorkeur direct via GitHub-commit op de PR-branch, of via een kleine veilige lokale opdracht.

### 3.2 Altijd CLS bovenaan PowerShell-blokken

Verboden:

- PowerShell-commando's zonder `CLS` aan de start.

Vaste vorm:

```powershell
CLS
$ErrorActionPreference = "Stop"
cd C:\Users\Gebruiker\Rezzerv_Github
```

### 3.3 Geen lukrake wachttijden

Verboden:

- `Start-Sleep -Seconds 5`
- Andere willekeurige sleep-tijden.
- Verkorte Docker-herstart zonder protocol.

Maatregel:

- Alleen het vastgelegde Rezzerv-protocol gebruiken.
- Bij rebuild/runtime-mismatch: gedocumenteerde rebuild-route met juiste wachttijd, healthcheck en regressie.

### 3.4 Geen lokale npm-route bij bekende npm/Node-problemen

Verboden als primaire validatie:

- `npm install`
- `npm ci`
- `npm run build`

Maatregel:

- Docker-validatie gebruiken.
- Lokale npm/Node 25-problemen niet opnieuw als codefout interpreteren.

### 3.5 Geen aannames over draaiende versie

Verboden:

- Zeggen dat UI goed is zonder te controleren welke head draait.
- Aannemen dat browser en branch gelijklopen.
- Screenshots negeren die een oude bundle tonen.

Maatregel:

- Altijd versiebron vaststellen met `git rev-parse --short HEAD`.
- Bij UI-afwijking controleren of browser, frontendcontainer en branch dezelfde versie tonen.

### 3.6 Geen PR merge-ready verklaren zonder volledige PO- en regressiecheck

Verboden:

- PR uit draft halen op alleen codebasis.
- Merge-ready noemen zonder PO-check.
- Merge-ready noemen terwijl UI-afwijkingen openstaan.

Maatregel:

- Draft blijft draft totdat technische validatie groen is, UI/PO-check akkoord is, `git status --short` schoon is en alle blockerpunten zijn opgelost.

### 3.7 Geen component-one-offs

Verboden:

- Beheerpagina's from scratch bouwen.
- Eigen HTML-tables gebruiken waar Rezzerv `Table` hoort.
- Eigen layout verzinnen naast bestaande beheerpatronen.
- Functionaliteit toevoegen zonder architectuurcheck.

Maatregel:

- Hergebruik standaardcomponenten:
  - `AppShell`
  - `Card`
  - `Button`
  - `Table`
  - `ResizableHeaderCell`
  - `useResizableColumnWidths`
  - `buildTableWidth`
  - bestaande modal-/actiepatronen

### 3.8 Geen afwijkende UI bij vergelijkbare beheerfuncties

Verboden:

- Artikelgroepen anders laten ogen dan Locaties.
- Losse input bovenaan voor toevoegen.
- Lege toestanden buiten tabelstructuur.
- Actieknoppen op andere plekken.
- Kolommen niet resizebaar maken.

Maatregel:

- Artikelgroepen moet qua look-and-feel het Locaties-patroon volgen.

### 3.9 Geen automatische Artikelgroep-logica

Verboden:

- Standaard Artikelgroepen aanmaken.
- Artikelgroepen automatisch toewijzen.
- Artikelgroepen afleiden uit barcode.
- Artikelgroepen afleiden uit externe databases.
- Artikelgroepen laten wijzigen door Uitpakken.
- Productherkenning bestaande Artikelgroep laten overschrijven.

Maatregel:

- Artikelgroep is uitsluitend handmatige gebruikersordening binnen huishouden.

### 3.10 Geen vermenging met productgroepen, GTIN of globale producten

Verboden:

- Artikelgroep koppelen aan global product.
- Artikelgroep koppelen aan GTIN.
- Artikelgroep laten functioneren als productcategorie.
- Artikelgroep mengen met bestaande productgroep-taxonomie.

Maatregel:

- Artikelgroep hoort bij huishoudelijk voorraadartikel.
- Technische `household_article` identiteit blijft het anker.

### 3.11 Geen onduidelijke foutafhandeling voor Voorraad

Verboden:

- Voorraad laten crashen door ontbrekende helperfunctie.
- Runtimefout verpakken als onbekend probleem.
- Zonder concrete oorzaak doorgaan met nieuwe features.

Maatregel:

- Bij fout eerst oorzaak isoleren:
  - console/runtimefout
  - ontbrekende functie/import
  - exact bestand
  - exacte herstelactie

### 3.12 Geen gegenereerde testoutput committen

Verboden:

- `frontend/playwright-report/`
- `frontend/playwright/`
- `frontend/test-results/`

Maatregel:

- Na regressie altijd opruimen en `git status --short` controleren.

### 3.13 Geen blind patchen op basis van oude context

Verboden:

- Patchen op basis van eerdere snippets zonder actuele lokale/GitHub-context.
- Patchanker gokken.
- Meerdere wijzigingen tegelijk zonder tussencontrole.

Maatregel:

- Eerst:
  - `git status --short`
  - relevante `Select-String` of GitHub fetch
- Dan pas minimale wijziging.

### 3.14 Geen technische uitleg als om maatregelen wordt gevraagd

Verboden:

- Excuses geven als vervanging voor maatregel.
- Lange verklaring zonder procedurele correctie.

Maatregel:

- Antwoord moet bevatten:
  - wat is de blokkade
  - welke regel is geschonden
  - welke maatregel voorkomt herhaling
  - welke concrete volgende stap veilig is

### 3.15 Geen vervolgcommando's die in `>>` kunnen eindigen

Verboden:

- Commando's met onafgesloten quotes.
- Here-strings.
- Lange scriptblokken met geneste braces.
- Complexe multiline strings in PowerShell.

Maatregel:

- Kleine commando's.
- Geen here-strings.
- Bij grotere codewijziging: via GitHub update/commit of bestandspatch met veilige methode.

## 4. Vaste werkwijze voor Rezzerv-codewijzigingen

```text
1. Eerst actuele status/context ophalen.
2. Dan oorzaak benoemen.
3. Dan minimale wijziging.
4. Dan vaste validatie.
5. Dan pas commit/push/PR-body.
```

## 5. Vaste read-only contextcheck

Gebruik deze stap voordat een lokale herstelactie wordt voorgesteld.

```powershell
CLS
$ErrorActionPreference = "Stop"
cd C:\Users\Gebruiker\Rezzerv_Github

git status --short
```

Aanvullend per situatie:

```powershell
Select-String -Path <bestand> -Pattern "<zoekterm>" -Context 5,20
```

## 6. Vaste validatie

Gebruik geen alternatieve validatieblokken.

```powershell
CLS
$ErrorActionPreference = "Stop"
cd C:\Users\Gebruiker\Rezzerv_Github

git diff --check origin/main...HEAD
git diff --stat origin/main...HEAD
python -m compileall backend\app
.\scripts\run-frontend-regression-report.ps1 -SkipDockerBuild

Remove-Item -Recurse -Force frontend\playwright-report, frontend\playwright, frontend\test-results -ErrorAction SilentlyContinue

git status --short
```

## 7. Runtime- of versiemismatch

Bij vermoeden dat browser/frontendcontainer/branch niet overeenkomen:

- Geen willekeurige sleep gebruiken.
- Geen verkorte herstart verzinnen.
- Vastgelegde Rezzerv rebuild-/healthcheck-route gebruiken.
- Daarna regressie draaien.
- Daarna `git status --short` controleren.

## 8. PR-beleid

Een PR blijft draft totdat:

- laatste branch-head lokaal is opgehaald;
- technische validatie groen is;
- relevante UI/PO-check akkoord is;
- regressie-output is opgeruimd;
- `git status --short` schoon is;
- de gebruiker expliciet opdracht geeft om ready/merge te doen.

## 9. Huidige blockerregel voor PR #155

Voor PR #155 geldt aanvullend:

```text
Voorraad mag niet crashen.
Ontbrekende helperfuncties in Voorraad.jsx moeten eerst veilig worden hersteld.
Geen nieuwe featurestappen totdat /voorraad weer opent.
```

## 10. Starttekst voor nieuwe chats

Gebruik in een nieuwe Rezzerv-chat deze verwijzing:

```text
Lees en volg Rezzerv-Werkinstructies-AI.md als harde werkinstructie. Geen here-strings, geen lange PowerShell-patches, altijd CLS boven PowerShell-blokken, geen lokale npm-route als primaire validatie, geen willekeurige sleeps, geen aannames over branch/runtime, en PR blijft draft tot PO-check en regressie akkoord zijn.
```

## 11. Artikelgroepen naast universele artikelnamen

### 11.1 Begrippen strikt scheiden

- **Universele artikelnaam** hoort bij de gestandaardiseerde productlaag (`global_products`).
- **Huishoudartikel** is het functionele anker binnen één huishouden (`household_article_id`).
- **Artikelgroep** is uitsluitend handmatige huishoudordening (`article_group_id`).
- Artikelgroep is geen productcategorie, geen GTIN-classificatie en geen externe-database-uitkomst.

Verboden:

- Artikelgroep automatisch aanmaken of toewijzen.
- Artikelgroep afleiden uit barcode, GTIN, kassabon, winkelcode, productnaam of externe kandidaat.
- Een bestaande Artikelgroep overschrijven door productherkenning of verrijking.
- Artikelgroepen tussen huishoudens delen of koppelen.

### 11.2 Directe sleutel verplicht

Voor Voorraad en Artikelgroepen geldt:

- Gebruik `inventory.household_article_id` en `row.householdArticleId` rechtstreeks.
- Gebruik geen naamgebaseerde resolver of join als structurele oplossing.
- `inventory_events` bewaart eveneens `household_article_id` voor nieuwe mutaties.
- Een backfill is pas akkoord als ontbrekende en ongeldige verwijzingen beide nul zijn.

### 11.3 Household-scoping is ook verplicht voor devroutes

Elke productie-, dev-, preview-, fixture- en diagnoseroute moet:

1. de actieve household-context uit de geautoriseerde request bepalen;
2. expliciet filteren op `household_id`;
3. voorkomen dat records van bijvoorbeeld `1` en `demo-household` in één UI-response worden gemengd.

Een patroon waarbij sommige Artikelgroepen wel en andere niet opgeslagen kunnen worden, wordt eerst onderzocht op household-scope en sleuteldata. Niet direct de frontend herschrijven en geen records naar een ander huishouden migreren om het symptoom te verbergen.

### 11.4 Rollen en UI-contract

- Beheerder kan Artikelgroepen toevoegen en toewijzen.
- Lid met mutatierecht kan toewijzen/wijzigen, maar niet automatisch nieuwe groepen aanmaken.
- Viewer ziet de groep maar de selectie is disabled.
- Succes blijft persistent na terugkeer en `Ctrl+F5`.
- Bij falen: rollback naar vorige selectie en begrijpelijke feedback; geen blijvende rode inline fout in de tabel.

## 12. Diagnose- en commandoverbeteringen na Artikelgroepvalidatie

### 12.1 Geen vals groen na een fout commando

Een losse `Write-Host CONTROLE_..._VOLTOOID` na een falende opdracht is geen bewijs. Als de query of Python-opdracht faalt, is de controle niet uitgevoerd.

Maatregel:

- Beoordeel exitcode en feitelijke output.
- Gebruik parameterized SQL in plaats van kwetsbare quoteconstructies.
- Houd PowerShell- en Python-strings eenvoudig.
- Na herhaalde quoteproblemen: stop en kies een klein downloadbaar script of een eenvoudiger read-only commando.

### 12.2 Vaste validatie voor Artikelgroepen

Minimaal bewijs vóór PO-acceptatie:

1. `python -m compileall backend\app` groen.
2. `git --no-pager diff --check` zonder inhoudelijke fouten.
3. Docker rebuild via `down` en `up -d --build`.
4. `Start-Sleep -Seconds 90`.
5. `/api/health` groen.
6. Containercode bevat household-filter en directe `household_article_id`-selectie.
7. API-data bevat uitsluitend het actieve huishouden.
8. Browsertest bewijst toewijzen, wijzigen en persistentie na refresh.
9. Viewer-/beheerderrechten zijn gecontroleerd.
10. Regressie-artefacten zijn opgeruimd en `git status --short` bevat alleen bedoelde wijzigingen.



## 9. Aanvulling v9 - Actuele werkwijze na PR #155

Deze aanvulling is normatief vanaf `main @ 8e9f8d41`. Zij verwerkt de fouten en verbeteringen uit de laatste merge- en validatiesessie.

### 9.1 Eerst documentatie en actuele bron lezen

- Bij een expliciete verwijzing naar Rezzerv-documentatie wordt die documentatie vóór een commando of implementatievoorstel gelezen.
- Bij twijfel over Dockerpaden, testvorm of mergeflow wordt niet op geheugen gehandeld.
- De actuele lokale bron of GitHub-PR wordt opgehaald voordat een selector, endpoint, responsecontract of patchanker wordt vastgesteld.
- Een antwoord mag niet beweren dat documentatie is gecontroleerd als dat niet aantoonbaar is gebeurd.

### 9.2 Docker is de normatieve runtime

- Backend hostpoort: `8011`; frontend hostpoort: `5174`.
- In de backendcontainer is `/app` de backend-root.
- Productcode staat onder `/app/app`; tests staan onder `/app/tests`; database staat op `/app/data/rezzerv.db`.
- Een nieuw hostbestand is niet automatisch aanwezig in een image-backed container. Eerst `docker compose up -d --build`.
- Na rebuild altijd `Start-Sleep -Seconds 90` vóór healthcheck.
- Geen lokale npm-route als primaire validatie.

### 9.3 Geen pytest-installatie in runtimecontainers

Verboden:

- `pip install pytest` in de backendruntime.
- Een pytest-afhankelijke test aan de PO geven wanneer pytest niet in de stack zit.

Verplicht:

- Bestaande Rezzerv-runner of self-contained Python-test.
- Gewone assertions, duidelijke `PASS`/`FAIL`, samenvatting en exitcode `1` bij fout.
- Uitvoering met `PYTHONPATH=/app python tests/<selftest>.py`.

Referentie:

```text
tests/test_off_search_service_contract_selftest.py
PASS manual_search_contract
PASS automatic_search_contract
RESULT 2/2 checks passed
OFF_SEARCH_SERVICE_CONTRACT_GREEN
```

### 9.4 Geen trial-and-error bij tests en selectors

- Lees eerst het echte component, endpoint of servicecontract.
- Gebruik expliciete ARIA-rollen en bestaande `data-testid`-waarden.
- Wanneer console-output geen URL bevat, voeg eerst gerichte netwerkdiagnostiek toe.
- Pas een testverwachting alleen aan als het goedgekeurde functionele contract de implementatie ondersteunt.
- Providerquery en gerapporteerde query worden afzonderlijk beoordeeld.
- Na twee mislukte aannames: stop, volledige context ophalen en één definitieve reparatie maken.

### 9.5 Tijdelijke OFF-search versus permanente koppeling

- `POST /api/external-products/off/search` is read-only.
- Searchresultaten leven in frontendstate en worden bij een nieuwe zoekactie vervangen.
- Search muteert geen voorraad, global product of externe kandidaatopslag.
- Definitieve koppeling is een afzonderlijke expliciete actie.
- Een bestaande cataloguskoppeling blijft gescheiden van tijdelijke resultaten.
- Canonieke receipt-itemidentiteit is brongekwalificeerd, bijvoorbeeld `purchase-import-line:<id>`.

### 9.6 Producttypebesluit voor de volgende fase

- Producttype is een merk- en verpakkingsonafhankelijke laag boven `global_product`.
- Artikelgroep blijft huishoudspecifieke handmatige ordening.
- Bij definitief koppelen aan een universeel artikel wordt ook Producttype onderhouden.
- Universeel artikel, Producttype en household-articlekoppeling worden atomair opgeslagen.
- Productmatching veroorzaakt geen voorraadmutatie.
- Alleen bevestigde primaire mappings tellen mee in aggregatie.
- Aggregatie gebruikt genormaliseerde inhoud in volume, gewicht of stuks.
- Externe databases leveren voorstellen; Rezzerv beheert de permanente mapping.

### 9.7 Verplichte afronding op main

Een featurebranch is niet afgerond na push of groene regressie.

Volgorde:

1. Featurebranch technisch en functioneel groen.
2. Commit en push.
3. PR controleren en mergen met de bedoelde head SHA.
4. `main` lokaal ophalen; `HEAD` en `origin/main` moeten gelijk zijn.
5. `docker compose down` en `docker compose up -d --build`.
6. 90 seconden wachten en health controleren.
7. Relevante backendselftest uitvoeren.
8. Centrale frontendregressie uitvoeren.
9. Regression-seeds controleren.
10. PO-smoketest uitvoeren.
11. Alleen dan: **GROEN OP MAIN en afgerond**.

Actuele referentie-uitkomst na PR #155:

```text
main: 8e9f8d41
OFF-contract-selftest: 2/2
Frontendregressie: 22/22
Runtime regression-seeds: 0
PO-smoketest: akkoord
```


## Kassabonketentest en artikelmodel (v10-aanvulling)
- Gebruik voor lokale PO-uitvoering: `.\scripts\run-receipt-inventory-chain.ps1`.
- Rapporteer iedere stap met status, stapnummer, percentage, verwacht en actueel.
- Iedere merge naar `main` moet de post-merge ketenworkflow starten.
- Bewaak de scheiding: universeel artikel = concreet centraal product; Producttype = centrale semantische aggregatie; Artikelgroep = handmatige huishoudindeling.
