# PR4 — Winkelkoppelingen tijdens de onboarding

## Doel
Een nieuwe beheerder die kassabonnen heeft ingeschakeld kan na het afronden van de huishoudinrichting direct de bestaande digitale winkelkoppelingen gebruiken. Bestaande huishoudens en Instellingen → Winkelkoppelingen blijven werken.

## Uitvoering
- Alleen bij backend-onboardingstatus `completed`, `can_manage` en `receipt_processing_enabled` volgt `/onboarding/winkels`.
- Die route is via de bestaande autorisatie `household_settings.manage` beveiligd.
- De bestaande winkelkoppelingen en importverwerkingen worden hergebruikt; onboarding beperkt de keuze tot AH, Lidl en Jumbo.
- AH OAuth mag na controle van dezelfde host naar exact `/onboarding/winkels` terugkeren; andere returnpaden blijven verboden.
- Een beheerder mag winkels nu koppelen of later vanaf Instellingen. Bestaande bonnen, historische voorraad en matching worden niet aangepast.
- Lidl/Jumbo vereisen nog steeds een browserfavoriet en expliciete actie; niet alle mobiele browsers ondersteunen dit.

## Gerichte controle
- `node frontend/tests/onboarding-store-connections.contract.mjs`
- `node frontend/tests/onboarding-choice-visibility.contract.mjs`
- `node frontend/tests/store-connections.contract.mjs`
- `python -m pytest -q backend/tests/test_kassa_ah_oauth_proxy.py`
- Fullstack browseracceptatie `frontend/tests/e2e/p0-onboarding.fullstack.spec.js` dekt nu ook de optionele winkelstap.

## Buiten PR4
De uniforme historische importvoortgang (PR5), het doorvoeren van koopritmes in Bijna op (PR6) en de praktijkacceptatie met echte winkelaccounts (PR7) volgen afzonderlijk. AH-import blijft afhankelijk van de bestaande platformpauze en configuratie. Geen productieactie of merge is onderdeel van deze PR.
