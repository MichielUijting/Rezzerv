# Rezzerv Receipt Ingestion Engine - migratiekaart

Versie: R9-35A
Status: inventarisatie en doelmapping, geen functionele runtime-wijziging

## Doel

Deze migratiekaart legt vast waar bestaande receipt-ingestion code nu staat, waar deze volgens de doelarchitectuur hoort en welk risico een migratie heeft.

## Classificaties

| Type | Betekenis |
|---|---|
| pipeline | orchestration/routering/result assembly |
| extraction | OCR, PDF, email, html, preprocessing |
| core | generieke parsing helpers |
| profile | winkelspecifieke interpretatie |
| service | API/database/service facade |
| status | SSOT statusbepaling |
| diagnostics | uitlegbaarheid en debug-export |

## Inventarisatie huidige bestanden

| Huidige locatie | Gewenste locatie | Type | Risico | Opmerking |
|---|---|---|---|---|
| `backend/app/services/receipt_service.py` | `receipt_ingestion/pipeline/*`, `extraction/*`, `profiles/*`, service facade | mixed/service | hoog | Te groot bestand; bevat orchestration, OCR, parsers, store-specific uitzonderingen en databaseflow. |
| `backend/app/receipt_ingestion/header_parser.py` | `core/header_common.py` + `profiles/<chain>/header.py` + `profiles/<chain>/totals.py` | mixed/core/profile | hoog | Bevat generieke store/date parsing en winkelspecifieke total logic. |
| `backend/app/receipt_ingestion/amounts.py` | `receipt_ingestion/core/amounts.py` | core | laag | Generieke bedragenlogica; kan later veilig worden verplaatst of via re-export behouden. |
| `backend/app/receipt_ingestion/line_classifier.py` | `receipt_ingestion/core/line_classifier.py` | core | middel | Controleren op winkelnaam-specifieke regels voordat wordt verplaatst. |
| `backend/app/receipt_ingestion/product_candidate_gateway.py` | `receipt_ingestion/core/product_candidate_gateway.py` | core | laag | Generieke candidate builder. |
| `backend/app/receipt_ingestion/structured_product_gateway.py` | `receipt_ingestion/core/structured_product_gateway.py` | core | laag | Generieke structured candidate builder. |
| `backend/app/receipt_ingestion/parser_diagnostics.py` | `receipt_ingestion/core/diagnostics.py` of `diagnostics/parser_diagnostics.py` | diagnostics/core | laag | Generieke parserdiagnostics. |
| `backend/app/receipt_ingestion/parser_debug_serializer.py` | `receipt_ingestion/diagnostics/parser_debug_serializer.py` | diagnostics | laag | Debug serialization gescheiden houden van parserlogica. |
| `backend/app/receipt_ingestion/fingerprints.py` | `receipt_ingestion/core/fingerprints.py` | core | laag | Generieke fingerprint helpers. |
| `backend/app/receipt_ingestion/preprocessing/*` | `receipt_ingestion/extraction/preprocessing/*` | extraction | middel | Technische preprocessing; geen winkelregels toestaan. |
| `backend/app/receipt_ingestion/profiles/base.py` | behouden als `profiles/base.py` | profile | laag | Uitbreiden met formeel profielcontract. |
| `backend/app/receipt_ingestion/profiles/ah_runtime.py` | `profiles/ah/articles.py`, `profiles/ah/filters.py`, `profiles/ah/diagnostics.py` | profile | middel | AH-artikelregels al deels afgescheiden, maar nog niet modulair genoeg. |
| `receipt_status_baseline_service_v4.py` | behouden buiten parserprofielen | status | hoog | Enige bron voor functionele status. Niet mengen met parser/profielen. |

## Eerstvolgende migratievolgorde

### R9-35A - architectuuranker

- ARCHITECTURE.md toevoegen.
- MIGRATION_MAP.md toevoegen.
- Mappenstructuur aanmaken.
- Profielinterface en registry-skeleton toevoegen.
- Geen functionele parserwijziging.

### R9-35B - AH totals isoleren

- AH-total logic uit `header_parser.py` naar `profiles/ah/totals.py`.
- Generieke header_parser laat alleen generieke fallbackvrije header-primitives over.
- Acceptatie: AH foto 2 blijft goed; AH foto 3 gebruikt alleen expliciete AH-total anchors als die in parser-input aanwezig zijn.

### R9-35C - AH articles isoleren

- `ah_runtime.py` opsplitsen naar `profiles/ah/articles.py` en `profiles/ah/filters.py`.
- Geen gedragswijziging tenzij expliciet getest.

### R9-35D - store_branch profile-aware maken

- Generieke store_branch extractie beperken.
- AH-filiaalregels naar `profiles/ah/header.py`.
- Artikelregels mogen nooit als `store_branch` eindigen.

### R9-35E - receipt_service afslanken

- Source extraction naar `extraction/`.
- Parse orchestration naar `pipeline/parse_orchestrator.py`.
- `receipt_service.py` wordt service facade voor database/API.

## Migratieregels

1. Elke verplaatsing moet eerst zonder functionele wijziging gebeuren.
2. Daarna pas inhoudelijke verbeteringen, per winkelprofiel.
3. Geen nieuwe winkelregel in `receipt_service.py` of generieke core modules.
4. Geen filename-hacks in generieke pipeline.
5. Geen fallback naar artikelregelsom als totaalbedrag.
6. Diagnose mag productiegegevens niet wijzigen.

## Openstaande bekende issues

| Issue | Gewenste eigenaar |
|---|---|
| AH foto 3 total_amount blijft null ondanks raw OCR `TE BETALEN 5,40` | `profiles/ah/totals.py` na R9-35B |
| AH store_branch bevat artikelregels | `profiles/ah/header.py` na R9-35D |
| AH PDF/App totalen lopen via verkeerde bron | `profiles/ah/totals.py` |
| Jumbo specifieke fallback in generieke parsefunctie | `profiles/jumbo/articles.py` of verwijderen |
| Grote `receipt_service.py` | `pipeline/` + `extraction/` migratie |
