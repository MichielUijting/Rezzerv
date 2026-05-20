# R7c-2 — supermarket receipt fixture registry

Status: supermarket-only inventory and governance step  
Branch: `sync/local-rezzerv-receipt-basis-v2`

## Doel

R7c-2 definieert de eerste gecontroleerde regression fixture registry voor supermarktkassabonnen.

Scope van deze stap:

- inventariseren;
- normaliseren;
- baseline-koppeling;
- regression governance.

Niet in scope:

- parserverbeteringen;
- OCR-tuning;
- statuslogica wijzigen;
- store-specific heuristics wijzigen.

## Achtergrond

R7b heeft receipt ingestion onderhoudbaarheidsboundaries aangebracht zonder parsergedrag bewust te wijzigen.

R7c verschuift de focus naar:

- fixture governance;
- regressiecontrole;
- reproduceerbaarheid.

De Product Owner heeft expliciet besloten dat de focus voorlopig uitsluitend ligt op supermarktkassabonnen totdat deze stabiel de doelstatus `Gecontroleerd` halen.

## Gebruikte bronnen

### ZIP-fixtures

```text
supermarkten.zip
```

Inhoud:

- 14 supermarktfixtures;
- mix van:
  - PDF;
  - JPG/JPEG;
  - PNG.

### Baseline

```text
Rezzerv Kassabon baseline V6.xlsx
```

Bevat:

- receipt registry;
- expected receipt metadata;
- expected receipt lines.

## Scope-definitie supermarkt

De volgende supermarktketens vallen binnen scope:

- Albert Heijn / AH;
- Aldi;
- Jumbo;
- Lidl;
- Plus.

Picnic is in baseline aanwezig maar niet opgenomen in de huidige supermarktfixture-ZIP.

## Expliciet uitgesloten in R7c-2

De volgende receipttypes zijn bewust uitgesloten:

- Action;
- Gamma;
- Hornbach;
- Bol;
- Coolblue;
- MediaMarkt;
- Karwei.

Reden:

De PO heeft besloten eerst supermarktflows volledig stabiel te krijgen voordat andere winkelcategorieën worden meegenomen.

## Huidige fixture-landschap

### ZIP-fixtures in scope

| Store | Bestand(en) |
|---|---|
| AH | AH App 1.pdf, AH foto 1.pdf, AH foto 2.jpeg, AH foto 3.jpg |
| Aldi | Aldi foto 1.jpg, Aldi foto 2.jpg |
| Jumbo | Jumbo App 1.png, Jumbo foto 1.jpeg, Jumbo foto 3.jpg |
| Lidl | Lidl App 1.png, Lidl App 2.png, Lidl App 4.pdf |
| Plus | plus foto 1.jpg, plus foto 2.jpg |

## Belangrijke observaties

### 1. Naamgevingsinconsistenties

Geconstateerd:

- `Jumbo app 1.png` versus `Jumbo App 1.png`;
- `.jpg` versus `.jpeg`;
- case-verschillen.

Daarom gebruikt de R7c-2 tooling genormaliseerde match keys.

### 2. Baseline ≠ ZIP

De baseline bevat meer receipts dan de ZIP.

Dat is momenteel toegestaan zolang expliciet vastligt:

- welke fixtures actief in regressiescope zitten;
- welke buiten scope vallen.

### 3. Supermarktfixtures zijn heterogeen

De supermarktfixtures bevatten:

- app-export PDFs;
- app-screenshots;
- mobiele foto's;
- perspectiefverschillen;
- OCR-noise;
- verschillende datumformaten.

Dat maakt deze set geschikt als eerste regression baseline.

## R7c-2 tooling

Toegevoegd:

```text
tools/check_r7c2_supermarket_fixture_registry.py
```

Eigenschappen:

- standalone;
- geen backend imports;
- geen SQLAlchemy;
- geen OCR-runtime;
- alleen read-only analyse.

## Tool-uitvoer

De tool rapporteert:

- totaal aantal ZIP-fixtures;
- supermarktfixtures in scope;
- baseline-supermarktreceipts;
- ontbrekende baseline-matches;
- baseline-receipts buiten ZIP;
- expliciet uitgesloten non-supermarkt receipts;
- duplicate fixture names.

## Voorbeeldgebruik

```powershell
python tools/check_r7c2_supermarket_fixture_registry.py `
  --zip "C:\Users\Gebruiker\Downloads\supermarkten.zip" `
  --baseline "C:\Users\Gebruiker\Downloads\Rezzerv Kassabon baseline V6.xlsx"
```

Optioneel:

```powershell
python tools/check_r7c2_supermarket_fixture_registry.py `
  --zip "C:\Users\Gebruiker\Downloads\supermarkten.zip" `
  --baseline "C:\Users\Gebruiker\Downloads\Rezzerv Kassabon baseline V6.xlsx" `
  --csv-out ".\tmp\r7c2_supermarket_registry.csv"
```

## Registry-doelmodel

Per fixture wordt minimaal vastgelegd:

- fixture_file;
- store;
- baseline_receipt_id;
- expected_total;
- expected_line_count;
- target_status;
- in_scope;
- match_status.

## Belangrijke architectuurregel

R7c-2 introduceert nog geen parserkwaliteitsoordeel.

Dus:

- geen parser score;
- geen OCR confidence score;
- geen automatische store quality ranking.

Alleen:

- fixture governance;
- regression inventory;
- deterministic matching.

## Definition of Done

R7c-2 is gereed wanneer:

- supermarktfixtures expliciet afgebakend zijn;
- baseline-koppeling reproduceerbaar is;
- non-supermarkt receipts expliciet uitgesloten zijn;
- fixture inventory standalone controleerbaar is;
- geen parsergedrag is gewijzigd.

## Aanbevolen vervolgstap

```text
R7c-3 — canonical supermarket fixture registry and deterministic IDs
```

Doel:

- stabiele fixture identifiers;
- canonical naming;
- deterministic regression references;
- fixture governance voorbereiden voor parser regression runners.
