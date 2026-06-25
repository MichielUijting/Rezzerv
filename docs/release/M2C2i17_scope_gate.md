# M2C2i-17 Scope Gate

## Basis

- Basiscommit: `9524eca627ff264e4d859309c2685015b5fd733c`
- Basis: `main` na M2C2i-16 / PR #94

## Releasecategorie

Backend feature.

## Hoofddoel

Dynamische retailer-aliaslearning voor externe productkandidaten.

## Niet wijzigen

- Geen UI-componenten.
- Geen voorraadmutaties.
- Geen definitieve product- of huishoudartikelkoppeling.
- Geen productnamen in Python-code.

## Risico

Nieuwe tabel wordt runtime via service aangemaakt. Lokale databasevalidatie is verplicht vóór merge.
