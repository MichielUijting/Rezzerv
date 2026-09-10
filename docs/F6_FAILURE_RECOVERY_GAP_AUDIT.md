# Fase 6 — Failure & Recovery Gap Audit

Statusdatum: 10 september 2026  
Baseline: `main@2e2bac74318fc2e73726ed68e1b29fef464fb619`  
Authority: `quality/acceptance/f6_failure_recovery_gap_audit.json`

## Doel

Fase 6 sluit niet opnieuw de normale P0-succesroutes; die staan op 14/14 closed en 0 residuals. Deze fase bewijst dat de applicatie ook bij fouten, onderbrekingen en retries veilig en begrijpelijk blijft.

De roadmapcategorieën zijn exact:

1. 401/403;
2. functionele 4xx;
3. gecontroleerde 5xx;
4. timeout/tijdelijke fout;
5. ongeldige import;
6. retry/dubbele request;
7. onderbroken keten;
8. veilige hervatting;
9. standaard gebruikersfeedback;
10. databaseconsistentie na fout.

## Actuele auditstand

Alle 14 gesloten P0-scenario's zijn tegen alle tien categorieën beoordeeld. Dat levert 140 beoordelingen op:

| Status | Aantal | Betekenis |
|---|---:|---|
| covered | 20 | voldoende production-relevant bestaand bewijs |
| partial | 60 | relevant bewijs bestaat, maar Fase-6 authority is nog niet compleet |
| gap | 37 | expliciete bouwopgave |
| N/A | 23 | niet materieel voor dit scenario |

De oorspronkelijke startaudit stond op 15 covered / 64 partial / 38 gap / 23 N/A. F6-01 Inventory bracht de audit naar 18/62/37/23. De groene Receipt sub-slice brengt `P0-RECEIPT-INVENTORY-ALMOSTOUT` voor `controlled_5xx` en `standard_user_feedback` van partial naar covered, waardoor de actuele stand 20/60/37/23 is. `db_consistency_after_error` was voor Receipt al covered en krijgt door deze sub-slice sterker rollbackbewijs.

De audit is bewust conservatief. Een frontendtest met mocks, een contracttest of indirect bewijs wordt niet opgewaardeerd tot volledige failure/recovery authority.

## Reeds sterke bouwstenen

- Account/session: stale server session levert expliciet 401 en beschermde browserroute keert terug naar Login.
- Household/authorization: rol- en household-isolation authorities bestaan op browser/API-grens.
- Receipt/Uitpakken: L4-05 bewijst echte dubbele browser-submit zonder dubbele voorraad/events.
- Platform Authority: L4-07 bewijst sessie-intrekking, 401 en geen huishoudprivilege-escalatie.
- F6-01 Inventory: proof run `34397204686` op candidate `c7f630b47e446fe59a4c61b8dcb29ac8c3889b2d` bewijst een echte gecontroleerde 500 via de browser, vaste gebruikersfeedback en exacte PostgreSQL-rollback zonder inventory-event.
- F6-01 Receipt: proof run `34448095919`, job `102777275844`, op candidate `d8dd6e25f3055404682c01a32cece1cc9c6d8d77` is volledig groen. De zichtbare browserflow krijgt exact HTTP 500, toont `Verwerken van bonregels is mislukt.`, toont geen ruwe interne API-fout en bewijst na reload dezelfde receipt/batch/regeltoestand.
- Dezelfde Receipt-proof bewijst in PostgreSQL dat `purchase_import_batches.processed_at` leeg blijft, de regelstatus en `processed_event_id` niet veranderen, inventory exact 0 rijen en 0 events bevat en Almost-out exact 0 effect heeft. De backendlog bewijst bovendien dat de test-only finalization failure-hook werkelijk is geraakt.
- Historical F5-14 borgt standaard API-foutfeedback op gerichte frontendpaden, maar telt binnen Fase 6 alleen als partial zolang de backendfout niet production-like door de echte keten loopt.
- Migration/startup heeft eigen schema/runtime/zero-residual safety authority en wordt niet kunstmatig als user-facing recoveryflow behandeld.

## Belangrijkste bevinding

Het grootste gedeelde P0-gat blijft **controlled 5xx + standaard gebruikersfeedback + bewezen PostgreSQL-consistentie**. Binnen F6-01 zijn Inventory en Receipt/Inventory/Almost-out nu gesloten voor de beoogde 5xx- en feedbackauthority. Voor Kassa Review en Uitpakken resteert nog aanvullende closure binnen deze slice.

## Uitvoeringsvolgorde

### F6-01 — Controlled 5xx + standard feedback + rollback

Scope: Receipt/Inventory/Almost-out, Kassa Review, Uitpakken en Inventory.

**Exit:** echte browser triggert gecontroleerde backendfout; gebruiker krijgt standaard begrijpelijke feedback; PostgreSQL bewijst nul ongewenste mutaties.

Actuele sub-slice-status:
- Inventory: closed;
- Receipt/Inventory/Almost-out: closed voor `controlled_5xx` + `standard_user_feedback`, met versterkte databaseconsistentie-authority;
- Kassa Review: open;
- Uitpakken: open.

### F6-02 — Timeout/temporary failure + safe retry/resume

Scope: Receipt/Inventory, Kassa Review en Uitpakken.

**Exit:** tijdelijke storing laat een consistente toestand achter; hervatting via zichtbare UI eindigt exact één keer correct.

### F6-03 — Invalid receipt/import fail-closed

Scope: Receipt/Inventory en Kassa Review.

**Exit:** ongeldige import wordt zichtbaar afgewezen en creëert geen foutieve receipt-, batch- of inventory-data.

### F6-04 — Interrupted mutation and safe resume

Scope: Onboarding, Settings Projection en Inventory.

**Exit:** onderbroken mutatie laat geen halve toestand achter en een volgende gebruikersactie kan veilig hervatten.

### F6-05 — Authorization + functional 4xx closure

Scope: Account/Session, Household Membership, Authorization/Isolation en Platform Authority.

**Exit:** bestaand 401/403-bewijs wordt centraal gesloten; alleen werkelijk ontbrekende functionele 4xx-varianten krijgen aanvullende tests.

## Werkwijze

Iedere slice volgt dezelfde regel:

1. bestaand bewijs eerst hergebruiken;
2. geen duplicaat-test bouwen wanneer authority al voldoende is;
3. nieuwe failure-injectie moet deterministisch en test-only geactiveerd zijn, nooit via productie-defaults;
4. browsermutaties lopen via zichtbare UI;
5. PostgreSQL-eindstaat wordt na de fout expliciet bewezen;
6. iedere gerepareerde productfout krijgt permanente regressieauthority;
7. de auditmatrix wordt na iedere slice bijgewerkt zodat `gap -> partial -> covered` traceerbaar blijft.

## Fase-6 harde exit

Fase 6 is pas afgerond wanneer geen releasekritieke failure/recovery categorie meer als `gap` staat en resterende `partial`-statussen aantoonbaar niet releaseblokkerend zijn of naar `covered` zijn gebracht. De centrale validator en CI-gate moeten die eindstaat afdwingen.