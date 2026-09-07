# Acceptance quality authorities

Deze map bevat twee verschillende, elkaar aanvullende authorities.

## `functional_acceptance_matrix.json`

Dit is de brede laag-inventarisatie van L1 t/m L4 per productscenario. Een `partial` op een lagere laag betekent niet automatisch dat er nog een releaseblokkerend P0-gat bestaat wanneer de release-relevante keten op een hogere productiegrens aantoonbaar is bewezen.

## `p0_residual_closure.json`

Dit is vanaf baseline `main@c7ef1a7a04d87fbcd37ea2164a95871e4c26515f` de actuele authority voor de vraag **welke P0-scenario's nog echt aanvullend testwerk nodig hebben**.

De closure is evidence-first:

- exact 14 P0-scenario's;
- 6 release-relevant gesloten;
- 8 expliciete residuals;
- F5-01 t/m F5-14 zijn historische regressieclosure en worden niet opnieuw als P0-gat opgevoerd;
- ieder closure-besluit noemt bestaande repository-evidence;
- `scripts/acceptance/validate_p0_residual_closure.py` controleert bron-blob-SHA's, evidencepaden, tellingen en F5-proof;
- `.github/workflows/p0-residual-matrix-closure.yml` is de CI-gate.

De acht residuals zijn daarmee de enige P0-testuitbreidingen die na deze audit nog als open implementatiewerk gelden. Centrale bundeling van alle gates tot één releasebeslissing hoort bij Fase 9 en is geen nieuw functioneel P0-scenario.
