# M2C2i-17 Release Gate

## Release Gate v1.10 – Compliance Check

Basisversie: `main` na PR #94 (`9524eca627ff264e4d859309c2685015b5fd733c`)

Nieuwe versie: nog niet vastgesteld; dit is een PR, geen release.

Releasecategorie: backend feature.

Wijzigingsdoel: dynamische retailer-aliaslearning voor externe productkandidaten.

Niet gewijzigd:
- UI-layout
- voorraadmutaties
- definitive productkoppelingen
- huishoudartikelen

Getest:
- Nog niet lokaal uitgevoerd in Docker.

Niet getest:
- Docker build
- backend runtime smoke
- UI bovenste tabel

Risiconiveau: middel. Nieuwe runtime-tabel en matchflowwijziging.

Database locatie: moet lokaal bevestigd worden via `/api/health`.

Database validatie: verplicht vóór merge.

Scope Gate: groen op afbakening.

QA/QC Gate: nog niet groen.

Packaging Gate: niet van toepassing voor PR; wel verplicht bij release.
