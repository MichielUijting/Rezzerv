# R7c33 Architecture Decision — Freeze legacy browser regression runner

## Besluit

De bestaande browser-regressierunner wordt niet verder gerepareerd.

## Bevroren onderdeel

```text
frontend/scripts/run-regression.mjs
```

## Nieuwe richting

Er komt een backend-only receipt validation runner:

```text
tools/r7c33_receipt_validation_runner.py
```

Deze nieuwe route valideert alleen de receipt/Kassa/Uitpakken-keten die nodig is voor de huidige OCR- en receipt-ingestion stap.

## Verbod

Geen nieuwe patches meer op:

```text
frontend/scripts/run-regression.mjs
```

Uitzondering:

```text
R7c34: verwijderen, deprecaten of verplaatsen naar deprecated/archive
```

## Reden

De oude browser-regressierunner heeft te veel orchestration-vervuiling:

- instabiele process lifecycle;
- shell/cmd/powershell-spawnvervuiling;
- poortconflicten;
- fixture-state leakage;
- te brede scope;
- risico op spooksoftware.

## Architect-gate

R7c33 mag pas als afgerond gelden wanneer:

1. de backend-only receipt validation runner groen of diagnostisch betrouwbaar is;
2. R7c34 expliciet is ingepland;
3. de oude browser-regressierunner verwijderd of gedegradeerd wordt naar deprecated/archive.
