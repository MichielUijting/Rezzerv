# Rezzerv documentatie-update - 18 juli 2026

Deze bundel verwerkt de merge van PR #155 naar `main @ 8e9f8d41` en de aansluitende main-validatie.

## Vastgelegde releasefeiten

- Featurecommit: `8eed8441`
- Mergecommit main: `8e9f8d41`
- Backend health: groen
- OFF-contract-selftest: 2/2 groen
- Centrale frontendregressie: 22/22 groen
- Runtime regression-seeds: 0
- PO-smoketest: akkoord
- Eindstatus: GROEN OP MAIN en afgerond

## Zwaar bijgewerkte onderwerpen

- Persistente en huishoudspecifieke Artikelgroepen
- Directe `household_article_id`-sleutels en household-scoping
- Canonieke `receipt_item_id`
- Tijdelijke, read-only Open Food Facts-search
- Scheiding tussen zoeken en permanent koppelen
- Universele artikelnaam in Instellingen, Uitpakken en Artikeldetail
- Docker-only backendvalidatie met self-contained Python-runners
- Verplichte post-merge validatie op main
- Besluit voor een nieuwe Producttype-laag
- Direct Producttype onderhouden bij koppeling aan een universeel artikel
- Merk- en leveranciersoverstijgende voorraadaggregatie in basiseenheden

## Nieuwe documentversies

- Functioneel Ontwerp v4.11
- Technisch Ontwerp v4.12
- QA/QC-handvest v9
- Werkinstructies AI v9
- Doelarchitectuur Platform v2.21
- Opstartroutine v1.11
- Development Stack v1.13


## Update 2026-07-19 - kassabonketentest
- PowerShell-runner met 8 zichtbare stappen toegevoegd.
- Ketentest verplicht bij PR en opnieuw bij iedere merge/push naar main.
- Artikelmodel vastgelegd: universeel artikel, Producttype en huishoudspecifieke Artikelgroep.
- Voorraadpad en idempotentie: 0 -> 2 -> 5 -> 5, exact twee purchase-events.
