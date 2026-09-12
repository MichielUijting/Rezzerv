# Acceptance quality authorities

Deze map bevat drie verschillende, elkaar aanvullende authorities.

## `functional_acceptance_matrix.json`

Dit is de brede laag-inventarisatie van L1 t/m L4 per productscenario. Een `partial` op een lagere laag betekent niet automatisch dat er nog een releaseblokkerend P0-gat bestaat wanneer de release-relevante keten op een hogere productiegrens aantoonbaar is bewezen.

## `p0_residual_closure.json`

Dit is vanaf baseline `main@c7ef1a7a04d87fbcd37ea2164a95871e4c26515f` de actuele authority voor de vraag **welke P0-scenario's nog echt aanvullend testwerk nodig hebben**.

De closure is evidence-first:

- exact 14 P0-scenario's;
- 7 release-relevant gesloten;
- 7 expliciete residuals;
- P0-ACCOUNT-SESSION is gesloten met echte browser-login als bestaande gebruiker, server-side logout, stale-cookie 401 en PostgreSQL-eindbewijs zonder actieve sessies;
- F5-01 t/m F5-14 zijn historische regressieclosure en worden niet opnieuw als P0-gat opgevoerd;
- ieder closure-besluit noemt bestaande repository-evidence;
- `scripts/acceptance/validate_p0_residual_closure.py` controleert bron-blob-SHA's, evidencepaden, tellingen en proof;
- `.github/workflows/p0-residual-matrix-closure.yml` is de CI-gate.

De zeven resterende residuals zijn daarmee de enige P0-testuitbreidingen die na deze eerste residual-closure nog als open implementatiewerk gelden. Centrale bundeling van alle gates tot één releasebeslissing hoort bij Fase 9 en is geen nieuw functioneel P0-scenario.

## `po_acceptance_pack.json`

Dit is de Phase 8 authority voor **F7-REL-02 / PO Acceptance**. Het pack vertaalt alle P0-scenario's waarvoor `manual_po_acceptance=true` naar vier korte, vaste gebruikersjourneys van samen circa 25 minuten.

Belangrijk:

- de PO beoordeelt gebruikersduidelijkheid, flow, feedback, productintentie en rol/context;
- geautomatiseerde regressie-, database-, API- en CI-bewijzen worden niet handmatig overgedaan;
- `P0-MIGRATION-STARTUP` blijft bewust technische release-authority en zit niet in het PO-pack;
- `po_acceptance_result.template.json` start altijd op `pending` en mag nooit automatisch acceptance verzinnen;
- `scripts/acceptance/validate_po_acceptance_pack.py` controleert fail-closed dat exact alle handmatige P0-scenario's zijn afgedekt, de check kort blijft en `F7-REL-02` open blijft tot een expliciet PO-resultaat;
- `.github/workflows/f8-po-acceptance-pack-validation.yml` borgt het pack-contract in CI.

De leesbare uitvoering staat in `PO_ACCEPTANCE_PACK.md`.
