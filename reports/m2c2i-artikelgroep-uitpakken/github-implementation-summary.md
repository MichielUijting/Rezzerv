# GitHub-implementatie M2C2i Artikelgroep-terminologie

Branch: `m2c2i-artikelgroep-uitpakken-terminology-github`
Base: `main` na PR #151

## Wijzigingen

1. `frontend/vite.config.js`
   - Voegt een kleine Vite pre-transform toe die frontendbronstrings `Mijn artikel` en `mijn artikel` omzet naar `Artikelgroep` en `artikelgroep`.
   - Hiermee verandert de zichtbare frontendterminologie zonder grote bulkedit in megabestanden.

2. `docs/architecture/M2C2i_artikelgroep_terminology.md`
   - Legt het functionele besluit vast: Artikelgroep is huishoudelijke ordening, geen productidentiteit.

3. `frontend/tests/e2e/artikelgroep-terminology.frontend-regression.spec.js`
   - Bewaakt dat de frontendbundle geen oude terminologie meer bevat.

## Niet geraakt

- Geen databasewijziging.
- Geen parserwijziging.
- Geen OCR- of receipt-ingestionwijziging.
- Geen voorraadmutatie.
- Geen externe kandidaatselectie.

## Validatie nodig

De branch moet lokaal nog worden gevalideerd met Docker build, backend health en frontend-regressie voordat merge naar main kan worden overwogen.
