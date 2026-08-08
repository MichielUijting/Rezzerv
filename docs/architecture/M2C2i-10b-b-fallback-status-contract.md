# M2C2i-10b-b — Fallbackstatus en kandidaatpresentatie

## Doel

Fallback- en unresolved-regels mogen niet meer aanvoelen als gewone externe kandidaten.

Een externe kandidaat is beslisondersteuning. Een fallback is alleen een informatieve regel waarmee Rezzerv uitlegt dat er geen echte externe match is gevonden. Een fallback mag daarom niet rechtstreeks koppelbaar zijn aan de artikelcatalogus.

## Scope

Deze stap borgt het contract tussen backend en frontend voor kandidaatstatussen in Externe databases.

### Statusgroepen

| Technische status | Gebruikerslabel | Koppelbaar | Telt als externe kandidaat |
|---|---|---:|---:|
| `linked_to_catalog` | Gekoppeld | nee | ja |
| `user_confirmed` | Kandidaat | ja, als backend dit toestaat | ja |
| `probable_candidate` | Waarschijnlijke kandidaat | ja, als backend dit toestaat | ja |
| `weak_candidate` | Lage zekerheid | ja, als backend dit toestaat | ja |
| `candidate` | Kandidaat | ja, als backend dit toestaat | ja |
| `fallback_candidate` | Geen externe match | nee | nee |
| `receipt_fallback_candidate` | Geen externe match | nee | nee |
| `receipt_unresolved_fallback` | Geen externe match | nee | nee |
| `unresolved_fallback` | Geen externe match | nee | nee |
| `unresolved` | Geen externe match | nee | nee |
| `no_external_match` | Geen externe match | nee | nee |

## Functionele regels

1. Fallbackregels blijven zichtbaar als uitleg, maar niet als normale externe match.
2. Fallbackregels mogen niet geselecteerd of gekoppeld worden.
3. Een bonartikel met alleen fallbackregels toont bovenin geen beste kandidaat en score.
4. De kolom `Externe kandidaten` telt alleen echte externe matches.
5. De detailtabel mag fallbackregels tonen met label `Geen externe match`.
6. De backend blijft leidend voor `is_linked_to_catalog` en `is_linkable_to_catalog`.
7. Geen enkele statuswijziging mag automatisch `global_products`, `product_enrichments`, `household_articles` of `inventory_events` aanmaken.

## Acceptatiecriteria

- Een echte kandidaat blijft zichtbaar en koppelbaar wanneer `is_linkable_to_catalog=true`.
- Een gekoppelde kandidaat blijft zichtbaar als `Gekoppeld`.
- Een fallbackstatus zoals `receipt_unresolved_fallback` toont `Geen externe match`.
- Een fallbackstatus is niet koppelbaar.
- Een fallbackstatus telt niet mee als externe kandidaat.
- De bestaande Externe-databases-regressies blijven groen.

## Voorgestelde technische wijziging

De kleinste veilige wijziging zit in `frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx`:

- fallbackstatussen centraal normaliseren;
- `candidateStatusLabel()` uitbreiden;
- fallbackregels markeren als `isFallbackCandidate`;
- fallbackregels niet meetellen in `candidateCount`;
- `bestCandidateForItem()` alleen echte externe matches laten kiezen;
- radioselectie uitschakelen voor niet-koppelbare fallbackregels;
- Playwright-regressie toevoegen met een `receipt_unresolved_fallback` fixture.

## Validatie na implementatie

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github

git fetch origin
git switch feature/m2c2i10b-fallback-status-contract

git branch --show-current
git status --short
git rev-parse --short HEAD

docker compose down
docker compose up -d --build

Start-Sleep -Seconds 90

Invoke-RestMethod http://localhost:8011/api/health

.\scripts\run-frontend-regression-report.ps1 -SkipDockerBuild
```
