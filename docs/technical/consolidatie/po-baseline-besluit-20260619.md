# PO-baselinebesluit 2026-06-19

## Besluit

De branch aseline/po-tested-consolidatie-20260619 wordt vanaf nu gebruikt als functionele PO-baseline voor de verdere ontwikkeling van Rezzerv.

## Basis

Deze baseline is gemaakt vanaf:

- vorige lokale branch: local/consolidatie-po-baseline
- commit: de24bcbf
- status: lokaal PO-getest en technisch opgeschoond

## Reden

De lokale omgeving is door de PO getest en functioneel akkoord bevonden voor de huidige kernflows:

- Home
- Kassa
- Uitpakken
- Externe databases

Daarnaast is de omgeving gecontroleerd via de gedocumenteerde Docker-opstart:

- docker compose down
- docker compose up -d --build
- backend healthcheck via /api/health
- browsercontrole van de kernflows

## Status van main

main is tijdelijk niet leidend voor de functionele voortgang.  
De PO-geteste baselinebranch is de werkbasis voor vervolgontwikkeling.

## Gebruik van oude branches

Niet-geïntegreerde branches worden niet automatisch gemerged.  
Ze mogen alleen worden gebruikt als referentiebron voor specifieke verbeteringen.

Per verbetering geldt:

1. probleem beschrijven;
2. relevante oude branch of commit inspecteren;
3. alleen het bruikbare deel overnemen;
4. lokaal testen;
5. klein en controleerbaar committen.

## Beschermde afspraken

De volgende afspraken blijven onverkort gelden:

- Kassabonstatus blijft SSOT via eceipt_status_baseline_service_v4.py.
- UI gebruikt po_norm_status_label.
- parse_status mag niet als categoriebron worden gebruikt.
- Kassa blijft invoerkanaal.
- Uitpakken blijft de brug naar voorraad.
- Voorraadmutatie gebeurt pas na artikel-, hoeveelheid- en locatietoewijzing.
- Externe productdata en Open Food Facts mogen geen automatische huishoudartikelen of voorraadmutaties aanmaken.

## Validatie van deze baseline

Laatste bekende validatie:

- backend compileall: OK
- frontend build: OK
- Docker Compose build/start: OK
- backend health: OK
- browsercontrole: OK
- git status: schoon

## Vervolg

Nieuwe functionele verbeteringen starten vanaf deze baselinebranch.
