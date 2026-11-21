# PR5 — Historische winkelimport met betrouwbare voortgang

## Functionaliteit
- In het onboarding- en instellingenscherm **Winkelkoppelingen** staat nu één duurzaam statusoverzicht voor AH, Lidl en Jumbo.
- Per winkel worden afzonderlijk getoond: reeds in Kassa opgeslagen bonnen, aantoonbaar bruikbare historische bonnen en Lidl/Jumbo-wachtrijstatussen (wachtend, bezig, beoordeling nodig).
- De telling leest bestaande PostgreSQL-bronbonnen en de duurzame importwachtrij. Het scherm haalt **geen** bonnen op en schrijft geen voorraad.
- Voor nieuwe huishoudens bepaalt de bestaande historische cutover of een bon voor historische analyse in aanmerking komt. De **oorspronkelijke, niet-standaard aankoopdatum** is doorslaggevend; een bon met onbekende/default datum telt nooit zomaar als historische aankoop.
- Bij bestaande huishoudens zonder cutover blijft het aantal historische bonnen **onbekend** in plaats van nul.
- De wachtrij blijft onder de bestaande platform- en onderhoudspauze. Het voortgangsoverzicht kan de pauze niet uitzetten.
- Bij lopende wachtrij wordt de telling periodiek bijgewerkt; handmatig vernieuwen is altijd mogelijk. Het overzicht blijft via Instellingen beschikbaar na het verlaten van onboarding.
- De bestaande AH-synchronisatie en browseroverdracht van Lidl/Jumbo blijven de enige toegestane ontvangstroutes. Dit biedt **geen** nieuwe toegang tot winkelaccounts, garandeert geen complete geschiedenis en maakt geen nieuwe importopdracht bij het openen van het scherm.

## Grenzen
- De API `GET /api/receipts/retailers/history-progress` accepteert geen `household_id` uit de browser. Hij gebruikt uitsluitend de bestaande geautoriseerde sessie en retourneert alleen tellingen (geen klantgegevens, boninhoud, accounttokens of externe bon-ID's).
- Bestaande duplicate-, matching-, historische cutover- en voorraadafboekregels blijven ongewijzigd.
- `queue_completed` is geen extra import boven op `kassa_receipts`: dubbeltelling moet vermeden worden.
- Bestaande AH-ophaalgrenzen (maximaal 100 per request) blijven gelden. Volledige dekking is pas aantoonbaar na praktijkacceptatie met winkelaccounts (PR7).

## Gerichte controles
- `python -m pytest -q backend/tests/test_retailer_history_progress.py`
- `node frontend/tests/historical-import-progress.contract.mjs`
- Frontendbuild, volledige contractset, backend-/huishoudisolatie- en ketenregressie via GitHub Actions vóór Ready.

## Vervolg van het onboardingprogramma
PR6 integreert de uit historie afgeleide herhaalaankooptermijnen en voorraadregels met **Bijna op**. PR7 toetst echte retaileraccounts en historiedekking. Niets in deze PR activeert een gepauzeerde winkelimport of voert productieacties uit.
