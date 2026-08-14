# Receipt lifecycle Release B

Status: implementation + pre-merge validation

## Doel

Release B implementeert het functionele gedrag voor verwijderen, archiveren, terugzetten en opnieuw inlezen van kassabonnen in **Kassa** en **Uitpakken**, boven op de in Release A toegevoegde `logical_receipt_key`, `logical_line_key` en `workflow_state`.

Release B introduceert **geen nieuwe datatabellen** en **geen tweede statuswaarheid**. Bestaande tabellen blijven canoniek:

- `receipt_tables` — bonidentiteit en workflowstatus;
- `receipt_table_lines` — bonregelidentiteit en Kassa-validatiestatus;
- `purchase_import_lines` — Uitpakken-/verwerkingsstatus;
- `inventory_events` — enige waarheid voor uitgevoerde voorraadmutaties.

## Productregels

### B1. Volledig verwijderen

Een bon volledig verwijderen betekent niet dat reeds uitgevoerde voorraadmutaties worden teruggedraaid.

Bij volledig verwijderen:

1. de actieve fysieke import (`receipt_tables` + `raw_receipts`) wordt soft-deleted;
2. `receipt_tables.workflow_state` wordt `removed_reimport_allowed`;
3. de originele `sha256_hash` blijft ongewijzigd;
4. `inventory_events` worden **niet** verwijderd;
5. bestaande `purchase_import_lines` worden **niet** verwijderd alleen omdat de Kassa-import wordt verwijderd;
6. dezelfde bron mag daarna opnieuw worden ingelezen.

Hiermee wordt het oude gedrag beëindigd waarbij delete via `remove_receipt_inventory_events()` reeds opgeborgen voorraad terugdraaide en waarbij de hash kunstmatig werd gemuteerd.

### B2. Herimport van exact dezelfde kassabon

Bij een nieuwe import met dezelfde huishouding + originele bronhash als een eerder volledig verwijderde bon:

1. de nieuwe fysieke import krijgt een nieuw technisch `raw_receipt_id` en `receipt_table_id`;
2. de nieuwe import hergebruikt de bestaande `logical_receipt_key`;
3. logisch gelijke bonregels hergebruiken de bestaande `logical_line_key`;
4. historisch reeds goedgekeurde/verwerkte regels worden niet opnieuw als onbehandelde regel aangeboden;
5. niet eerder goedgekeurde/verwerkte regels blijven opnieuw behandelbaar.

Er wordt dus geen oude rij fysiek heropend. Herimport is een nieuwe fysieke waarneming van dezelfde logische bon.

### B3. Gedeeltelijk goedgekeurde of verwerkte kassabon

De regelstatus wordt niet opnieuw gedupliceerd in een nieuwe ledger. Er zijn twee bestaande feiten die apart betekenis houden:

- `receipt_table_lines.is_validated` is de waarheid of de regel in **Kassa** al is goedgekeurd;
- `purchase_import_lines.processing_status` plus `processed_at`/`processed_event_id` is de waarheid of de regel in **Uitpakken** al definitief is verwerkt.

Voor iedere bewezen herkende `logical_line_key` geldt daarom:

1. **eerder goedgekeurd, nog niet uitgepakt:** de herimportregel blijft goedgekeurd in Kassa en komt in Uitpakken als `pending` beschikbaar;
2. **eerder goedgekeurd én uitgepakt:** de herimportregel blijft goedgekeurd en wordt in Uitpakken direct als reeds `processed` behandeld; er ontstaat geen nieuwe voorraadmutatie;
3. **eerder niet goedgekeurd:** de regel blijft onbehandeld en kan opnieuw in Kassa worden beoordeeld;
4. alleen een exacte, ondubbelzinnige lijnmatch mag historische goedkeurings-/verwerkingsfeiten erven.

Een herimport mag dus nooit een tweede `inventory_event` voor dezelfde reeds verwerkte logische aankoopregel veroorzaken, maar mag evenmin een nog niet uitgepakte goedgekeurde regel verloren laten gaan.

### B4. Duplicate- en archiefcontract

Een identieke bron die **nog actief** aanwezig is blijft een duplicate en wordt niet opnieuw geïmporteerd.

Alleen wanneer de eerdere fysieke import soft-deleted is en `workflow_state = removed_reimport_allowed` mag dezelfde bron opnieuw worden ingelezen.

Een gearchiveerde bon is nadrukkelijk **niet herimporteerbaar**:

1. `receipt_tables.workflow_state = archived`;
2. de actieve receipt wordt uit Kassa en Uitpakken verborgen;
3. `raw_receipts.deleted_at` blijft leeg zodat de bronhash gereserveerd blijft;
4. een herimportpoging geeft een specifieke Archiefmelding en maakt geen nieuwe receipt;
5. alleen een Admin kan de bestaande gearchiveerde receipt terugzetten naar Kassa.

### B5. Verwijderkeuze vanuit Uitpakken

Wanneer een kassabon vanuit Uitpakken wordt verwijderd, moet de gebruiker expliciet kiezen uit:

- **Terugzetten naar Kassa**;
- **Archiveren**;
- **Volledig verwijderen**;
- **Annuleren**.

Voor alle drie inhoudelijke acties geldt dat reeds uitgevoerde `inventory_events` intact blijven.

**Terugzetten naar Kassa** maakt de bestaande receipt opnieuw zichtbaar en behandelbaar in Kassa en wist `approved_at`, zonder verwerkte regels terug te draaien.

**Archiveren** verwijdert de receipt uit actieve werklijsten, behoudt lineage/historie en blokkeert herimport.

**Volledig verwijderen** gebruikt de veilige deleteflow uit B1 en staat herimport daarna toe.

### B6. Kassa lifecycle-authoriteit en refresh

`approved_at` is de autoriteit voor de overgang van Kassa naar Uitpakken. Een inhoudelijke PO-status zoals `Gecontroleerd` mag een bon niet uit Kassa verwijderen zolang `approved_at` leeg is.

Kassa gebruikt geen periodieke 60-secondenpolling. Tabellen worden eventgedreven vernieuwd bij concrete gebruikers-/navigatiehandelingen. Een succesvolle import of mutatie mag niet afhankelijk zijn van een periodieke timer om zichtbaar te worden.

## Technische implementatieregels

1. De Release-A partial unique index op `(household_id, sha256_hash) WHERE deleted_at IS NULL` blijft leidend.
2. `ingest_receipt()` blijft actieve duplicaten afvangen met `deleted_at IS NULL` en herkent gearchiveerde bronnen afzonderlijk.
3. Voor een nieuwe import wordt gezocht naar de meest recente expliciet herimporteerbare voorganger met dezelfde `household_id` en originele `sha256_hash`.
4. De nieuwe bon neemt diens `logical_receipt_key` over.
5. Nieuwe bonregels worden gematcht aan historische regels met een exacte lijnsignatuur: positie/index, genormaliseerd label, hoeveelheid, eenheid, eenheidsprijs en regeltotaal. Alleen een ondubbelzinnige match neemt `logical_line_key` over.
6. Een match mag alleen binnen hetzelfde huishouden en dezelfde exact-source lineage plaatsvinden.
7. Onzekere of dubbelzinnige lijnmatches worden niet geforceerd; zij krijgen een nieuwe logical key en blijven behandelbaar.
8. Bij een bewezen lijnmatch wordt de bestaande Kassa-validatie uit `receipt_table_lines.is_validated` hergebruikt.
9. Bij een bewezen lijnmatch wordt de bestaande definitieve Uitpakken-verwerking uit `purchase_import_lines` herkend; een nieuwe work-itemrij mag dan alleen de bestaande processed-fact refereren en geen nieuwe inventorymutatie veroorzaken.
10. Geen hard delete in de normale lifecycleflow.
11. Geen wijziging aan inventory-eventhistorie door terugzetten, archiveren of volledig verwijderen.
12. Geen parallelle lifecycle-tabellen of tweede statusledger.

## Acceptatiecriteria Release B

Release B is pas groen wanneer geautomatiseerd is bewezen dat:

1. actieve duplicate-import nog steeds wordt geweigerd/herkend;
2. volledig verwijderen geen `inventory_events` verwijdert;
3. volledig verwijderen de originele `sha256_hash` intact laat;
4. volledig verwijderen `workflow_state = removed_reimport_allowed` zet;
5. dezelfde bron daarna opnieuw kan worden geïmporteerd;
6. herimport dezelfde `logical_receipt_key` hergebruikt;
7. overeenkomende regels dezelfde `logical_line_key` hergebruiken;
8. een eerder in Kassa goedgekeurde maar nog niet uitgepakte regel goedgekeurd blijft en nog steeds uitpakbaar is;
9. reeds verwerkte regels niet opnieuw tot voorraadmutaties leiden;
10. nog niet goedgekeurde/verwerkte regels opnieuw behandelbaar zijn;
11. gedeeltelijke verwerking + volledige delete + herimport exact één voorraadmutatie per reeds verwerkte logische regel behoudt;
12. Terugzetten naar Kassa reeds verwerkte regels en inventory-events behoudt;
13. Archiveren de raw bron/hash en inventory-events behoudt;
14. een gearchiveerde bron niet opnieuw kan worden geïmporteerd;
15. Admin de bestaande gearchiveerde receipt kan terugzetten zonder tweede receipt aan te maken;
16. de Uitpakken-UI de drie lifecyclekeuzes plus Annuleren toont;
17. een gearchiveerde herimport precies één Archiefdialoog toont;
18. `Gecontroleerd` een bon niet uit Kassa verwijdert zolang `approved_at` leeg is;
19. periodieke 60-seconden Kassa-polling afwezig blijft;
20. de bestaande Kassa -> Uitpakken -> Voorraad -> Bijna op-keten groen blijft;
21. geen nieuwe datatabellen, parallelle ledgers of onnodige datakopieën ontstaan.

## Bindende pre-merge testpoort

PR #240 / Release B mag pas uit draft en richting merge wanneer **alle** onderstaande poorten groen zijn:

1. **GitHub CI** — `Receipt lifecycle Release B validation` en alle bestaande receipt/inventory/security/household regressiegates groen;
2. **Centrale frontendregressie** — `scripts/run-frontend-regression-report.ps1` volledig groen, inclusief de Release-B Playwright lifecycle-suite en de echte Kassa-importketen;
3. **Receipt/inventory ketentest** — `scripts/run-receipt-inventory-chain-v2.ps1` groen voor Kassa -> Uitpakken -> Voorraad -> Bijna op en idempotente purchase-events;
4. **Release-B backendketen** — foundation-, lineage- en samengestelde delete/reimport-regressietests groen;
5. **Testhygiëne** — regressiefixtures en Playwrightartefacten correct opgeruimd, werkmap schoon en `git diff --check origin/main...HEAD` groen;
6. **PO-acceptatie** — Terugzetten naar Kassa, Archiveren, Admin restore uit Archief, Volledig verwijderen en herimport functioneel geaccepteerd.

De lokale orkestratie van poorten 2 t/m 5 gebeurt via:

`scripts/run-receipt-lifecycle-release-b-premerge.ps1`

Eén rood punt is een releaseblokker.

## Buiten scope van Release B

Een algemeen Archief-beheerscherm met zoeken/filteren en bulkbeheer valt buiten Release B. Release B levert wel het archiefcontract, herimportblokkade en de Admin-restore vanuit de Kassa-archiefmelding.
