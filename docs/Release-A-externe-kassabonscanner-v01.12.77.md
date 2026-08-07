# Release A — externe kassabonscanner / scannerontkoppeling

Status: implementatiebranch
Basis: `Rezzerv-MVP-v01.12.76` / main `be8494ed9840813155deafe3925f87cc4e80f427`
Nieuwe versie: `Rezzerv-MVP-v01.12.77`
Categorie: Backend-release

## Hoofddoel
Plaats de bestaande Rezzerv OCR/parser achter de provider-neutrale `ReceiptScannerGateway`, zodat een latere externe scanner via hetzelfde contract kan worden aangesloten zonder Kassa, Uitpakken of Voorraad te wijzigen.

## Binnen scope
- `CanonicalReceiptV1`, `ScanRequestV1`, scanstatus en foutcontract.
- `ReceiptScannerProvider`, `ProviderRegistry` en `ReceiptScannerGateway`.
- `RezzervLegacyScannerAdapter`.
- `FakeScannerProvider`.
- Canonieke validatie en normalisatie naar het bestaande `ReceiptParseResult`.
- Server-side configuratie met `rezzerv-legacy` als enige Release-A provider.
- Contract-, gateway- en legacy-equivalentietests.
- Bestaande productie-ingest en reparse lopen via de gateway.

## Buiten scope
Geen externe productieprovider, webhook, providerkeuze in de browser, UI-wijziging, parserheuristiek, productmatching, Uitpakken-wijziging, Voorraad-wijziging, licentiemodel of databaseschemawijziging.

## Harde grens
Een scanner levert waarnemingen. Productkoppeling, gebruikerscontrole, Uitpakken en voorraadmutatie blijven Rezzerv-verantwoordelijkheid.

## Runtime
Release A verandert Docker, poorten en database niet. De actuele compose blijft:
- backend host 8011 -> container 8000
- frontend host 5174 -> container 80
- database `sqlite:////app/data/rezzerv.db`
- mount `./backend/data:/app/data`
