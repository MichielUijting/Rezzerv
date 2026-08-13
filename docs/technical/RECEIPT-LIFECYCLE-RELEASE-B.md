# Receipt lifecycle Release B

Status: implementation tranche

## Doel

Release B implementeert het functionele gedrag voor verwijderen en opnieuw inlezen van kassabonnen in **Kassa**, boven op de in Release A toegevoegde `logical_receipt_key`, `logical_line_key` en `workflow_state`.

Release B introduceert **geen nieuwe datatabellen** en **geen tweede statuswaarheid**. Bestaande tabellen blijven canoniek:

- `receipt_tables` — bonidentiteit en workflowstatus;
- `receipt_table_lines` — bonregelidentiteit en Kassa-validatiestatus;
- `purchase_import_lines` — Uitpakken-/verwerkingsstatus;
- `inventory_events` — enige waarheid voor uitgevoerde voorraadmutaties.

## Productregels

### B1. Verwijderen in Kassa

Een bon verwijderen in Kassa betekent niet dat reeds uitgevoerde voorraadmutaties worden teruggedraaid.

Bij verwijderen:

1. de actieve fysieke import (`receipt_tables` + `raw_receipts`) wordt soft-deleted;
2. `receipt_tables.workflow_state` wordt `removed_reimport_allowed`;
3. de originele `sha256_hash` blijft ongewijzigd;
4. `inventory_events` worden **niet** verwijderd;
5. bestaande `purchase_import_lines` worden **niet** verwijderd alleen omdat de Kassa-import wordt verwijderd;
6. dezelfde bron mag daarna opnieuw worden ingelezen.

Hiermee wordt het huidige gedrag beëindigd waarbij Kassa-delete via `remove_receipt_inventory_events()` reeds opgeborgen voorraad terugdraait en waarbij de hash kunstmatig wordt gemuteerd.

### B2. Herimport van exact dezelfde kassabon

Bij een nieuwe import met dezelfde huishouding + originele bronhash als een eerder verwijderde bon:

1. de nieuwe fysieke import krijgt een nieuw technisch `raw_receipt_id` en `receipt_table_id`;
2. de nieuwe import hergebruikt de bestaande `logical_receipt_key`;
3. logisch gelijke bonregels hergebruiken de bestaande `logical_line_key`;
4. historisch reeds goedgekeurde/verwerkte regels worden niet opnieuw als onbehandelde regel aangeboden;
5. niet eerder goedgekeurde/verwerkte regels blijven opnieuw behandelbaar.

Er wordt dus geen oude rij fysiek heropend. Herimport is een nieuwe fysieke waarneming van dezelfde logische bon.

### B3. Gedeeltelijk goedgekeurde kassabon

De regelstatus wordt niet opnieuw gedupliceerd in een nieuwe ledger. Er zijn twee bestaande feiten die apart betekenis houden:

- `receipt_table_lines.is_validated` is de waarheid of de regel in **Kassa** al is goedgekeurd;
- `purchase_import_lines.processing_status` plus `processed_at`/`processed_event_id` is de waarheid of de regel in **Uitpakken** al definitief is verwerkt.

Voor iedere bewezen herkende `logical_line_key` geldt daarom:

1. **eerder goedgekeurd, nog niet uitgepakt:** de herimportregel blijft goedgekeurd in Kassa en komt in Uitpakken als `pending` beschikbaar;
2. **eerder goedgekeurd én uitgepakt:** de herimportregel blijft goedgekeurd en wordt in Uitpakken direct als reeds `processed` behandeld; er ontstaat geen nieuwe voorraadmutatie;
3. **eerder niet goedgekeurd:** de regel blijft onbehandeld en kan opnieuw in Kassa worden beoordeeld;
4. alleen een exacte, ondubbelzinnige lijnmatch mag historische goedkeurings-/verwerkingsfeiten erven.

Een herimport mag dus nooit een tweede `inventory_event` voor dezelfde reeds verwerkte logische aankoopregel veroorzaken, maar mag evenmin een nog niet uitgepakte goedgekeurde regel verloren laten gaan.

### B4. Geen regressie op normale duplicate-detectie

Een identieke bron die **nog actief** aanwezig is blijft een duplicate en wordt niet opnieuw geïmporteerd.

Alleen wanneer de eerdere fysieke import soft-deleted is en `workflow_state = removed_reimport_allowed` mag dezelfde bron opnieuw worden ingelezen.

## Technische implementatieregels

1. De Release-A partial unique index op `(household_id, sha256_hash) WHERE deleted_at IS NULL` blijft leidend.
2. `ingest_receipt()` blijft actieve duplicaten afvangen met `deleted_at IS NULL`.
3. Voor een nieuwe import wordt gezocht naar de meest recente expliciet herimporteerbare voorganger met dezelfde `household_id` en originele `sha256_hash`.
4. De nieuwe bon neemt diens `logical_receipt_key` over.
5. Nieuwe bonregels worden gematcht aan historische regels met een exacte lijnsignatuur: positie/index, genormaliseerd label, hoeveelheid, eenheid, eenheidsprijs en regeltotaal. Alleen een ondubbelzinnige match neemt `logical_line_key` over.
6. Een match mag alleen binnen hetzelfde huishouden en dezelfde exact-source lineage plaatsvinden.
7. Onzekere of dubbelzinnige lijnmatches worden niet geforceerd; zij krijgen een nieuwe logical key en blijven behandelbaar.
8. Bij een bewezen lijnmatch wordt de bestaande Kassa-validatie uit `receipt_table_lines.is_validated` hergebruikt.
9. Bij een bewezen lijnmatch wordt de bestaande definitieve Uitpakken-verwerking uit `purchase_import_lines` herkend; een nieuwe work-itemrij mag dan alleen de bestaande processed-fact refereren en geen nieuwe inventorymutatie veroorzaken.
10. Geen hard delete in de normale Kassa-flow.
11. Geen wijziging aan inventory-eventhistorie bij Kassa-delete.

## Acceptatiecriteria Release B

Release B is pas groen wanneer geautomatiseerd is bewezen dat:

1. actieve duplicate-import nog steeds wordt geweigerd/herkend;
2. verwijderen in Kassa geen `inventory_events` verwijdert;
3. verwijderen de originele `sha256_hash` intact laat;
4. verwijderen `workflow_state = removed_reimport_allowed` zet;
5. dezelfde bron daarna opnieuw kan worden geïmporteerd;
6. herimport dezelfde `logical_receipt_key` hergebruikt;
7. overeenkomende regels dezelfde `logical_line_key` hergebruiken;
8. een eerder in Kassa goedgekeurde maar nog niet uitgepakte regel goedgekeurd blijft en nog steeds uitpakbaar is;
9. reeds verwerkte regels niet opnieuw tot voorraadmutaties leiden;
10. nog niet goedgekeurde regels opnieuw behandelbaar zijn;
11. gedeeltelijke verwerking + delete + herimport exact één voorraadmutatie per reeds verwerkte logische regel behoudt;
12. bestaande Kassa -> Uitpakken -> Voorraad -> Bijna op-keten groen blijft;
13. geen nieuwe datatabellen, parallelle ledgers of onnodige datakopieën ontstaan.

## Buiten scope van Release B

De drie keuzes bij verwijderen vanuit **Uitpakken** — terug naar Kassa, archiveren of volledig verwijderen — worden pas in de volgende tranche geïmplementeerd. Release B legt daarvoor wel de logische identiteit en herimportveiligheid vast, maar verandert het Uitpakken-delete-menu nog niet.
