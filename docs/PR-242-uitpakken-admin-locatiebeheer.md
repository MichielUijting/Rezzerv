# PR #242 — Uitpakken: Admin locatie/sublocatie toevoegen

**Status:** gemerged in `main`  
**Mergecommit:** `ca1b765cd04a8002f6ede9b821898191e499dc68`  
**Geteste PR-head:** `6fe7f2406757109ae059247bc638a80dc3a27ec1`

## Doel

Herstellen van de eerder beschikbare mogelijkheid om tijdens **Uitpakken** vanuit de hoofdtabel een locatie/sublocatie te kiezen en, voor een huishoud-Admin, een ontbrekende locatie of sublocatie direct toe te voegen zonder de bonregelcontext te verliezen.

## Root cause

De oorspronkelijke searchable locatiepicker in de hoofdtabel van Uitpakken is op 25 juli bij het toevoegen van het bonartikeldetail-overlay vervangen door een gewone `<select>` en alleen in het detailvenster behouden. Latere B3-locatieverwerking bouwde voort op die regressieve hoofdtabelbediening.

Tijdens het herstel is daarnaast een React-state race vastgesteld: na inline create was de serverlijst met locatieopties al vernieuwd, maar de save valideerde nog tegen oude `locationOptions`-state. Hierdoor werd de nieuw aangemaakte locatie/sublocatie niet deterministisch op dezelfde bonregel opgeslagen.

## Definitieve implementatie

- De hoofdtabel van Uitpakken opent opnieuw de searchable **Locatie / sublocatie kiezen**-picker.
- De hoofdtabelpicker gebruikt de bestaande B3-aware verwerking voor `STOCK`, `DIRECT_CONSUMPTION`, **Standaard gebruiken** en rollback.
- Admin-autorisatie gebruikt de canonieke sessie-authority.
- Admin krijgt **+ Nieuwe locatie**.
- Admin krijgt **+ Nieuwe sublocatie**, inclusief keuze van de bovenliggende locatie zodat ook de eerste sublocatie kan worden aangemaakt.
- Create gebruikt uitsluitend de bestaande `POST /api/spaces` en `POST /api/sublocations` routes.
- Na server-side opslag worden locatieopties direct opnieuw geladen.
- De vers opgehaalde opties worden rechtstreeks aan de save-logica doorgegeven, zodat auto-select niet afhankelijk is van React-render-timing.
- **Beheer locaties** blijft beschikbaar voor volledig beheer.
- Gewone leden krijgen de create-/beheeracties niet.
- Detailpicker en bulkpicker zijn functioneel niet gewijzigd.

## Niet gewijzigd

- geen nieuw datamodel;
- geen nieuwe locatie-CRUD-API;
- geen wijziging aan inventory-eventmodel;
- geen wijziging aan bulk-locatietoewijzing;
- geen wijziging aan detailpicker-default-location-flow;
- geen wijziging aan receipt lifecycle Release B.

## Permanente regressieborging

De wijziging is permanent geborgd met:

- uitvoerbare pytest source/backend-contracten;
- Playwright-test voor Admin: nieuwe locatie maken en direct selecteren;
- Playwright-test voor Admin: eerste/volgende sublocatie maken en direct selecteren;
- negatieve Playwright-test voor een gewoon lid;
- opname van deze suite in de centrale frontendregressierunner;
- niet-muterende GitHub validation met contracttests, production build, echte Chromium-regressie en `git diff --check`.

## Technisch bewijs vóór merge

Op PR-head `6fe7f2406757109ae059247bc638a80dc3a27ec1` waren groen:

- 4/4 gerichte Admin-/B3-/sourcecontracttests;
- production frontend build;
- 3/3 gerichte Chromium-tests;
- Authorization matrix acceptance;
- Frontend cookie session authority;
- Unpacking household location isolation;
- Inventory location household isolation;
- Day article Direct consumption no stock;
- Unpacking readiness article model validation;
- Receipt inventory chain validation en merge gate;
- `git diff --check`.

## Volledige lokale pre-merge bewijsvoering

De lokale vaste pre-merge runner eindigde volledig groen:

- **37/37** reguliere frontendregressietests;
- **8/8** seriële Meldingen/Superuser-tests;
- **5/5** geïsoleerde echte Kassa-importketentests;
- totaal **50/50 Playwright-tests groen**;
- Receipt → Voorraad → Bijna-op productieketentest **12/12 groen**;
- fixture cleanup `PASS`;
- werkmap/fixtures `CLEAN`.

## PO-acceptatie

De Product Owner heeft de echte gebruikersflow functioneel getest en geaccepteerd:

- locatiepicker vanuit Uitpakken werkt;
- nieuwe locatie toevoegen werkt;
- nieuwe locatie wordt direct geselecteerd;
- nieuwe sublocatie toevoegen werkt;
- nieuwe sublocatie wordt direct geselecteerd;
- gedrag is functioneel akkoord.

## Eindstatus

PR #242 is na technische QA/QC, ketenvalidatie en PO-acceptatie gemerged in `main` als:

`ca1b765cd04a8002f6ede9b821898191e499dc68`
