# Receipt lifecycle Release A

Status: implementatie in ontwikkeling  
Baseline: `main` @ `a4a4b623a28eecd9a0168e92aa3dc1b8cf54e546`

## 1. Doel

Release A legt alleen de minimale fundering voor veilig verwijderen, archiveren, herstellen en herimporteren van kassabonnen. De release verandert nog geen gebruikersgedrag in Kassa of Uitpakken.

Harde ontwerpregels:

- geen nieuwe receipt identity-tabellen;
- geen receipt-line processing-ledger naast bestaande tabellen;
- geen archiefkopieën;
- geen tweede inventory-ledger;
- geen redundant opgeslagen `approved`/`unpacked`-waarheid;
- vervangen code wordt in de release waarin het gedrag omschakelt verwijderd, niet als legacy fallback behouden.

## 2. Audit bestaande canonieke waarheden

| Functioneel feit | Bestaande canonieke bron | Release A besluit |
|---|---|---|
| Exact ingelezen bronbestand | `raw_receipts.sha256_hash` | behouden; niet dupliceren |
| Technische importpoging | `raw_receipts.id` + `receipt_tables.id` | behouden |
| Bonregels van die import | `receipt_table_lines` | behouden |
| Per-regel Kassa-validatie | `receipt_table_lines.is_validated` | behouden; geen tweede approval-flag |
| Naar Uitpakken gebrachte regel | `purchase_import_lines`, gekoppeld via `external_line_ref = receipt-line:<receipt_table_line.id>` | behouden |
| Uitpakverwerking | `purchase_import_lines.review_decision`, `processing_status`, `processed_at`, `processed_event_id` | behouden |
| Werkelijke voorraadmutatie | `inventory_events` | enige voorraadledger; behouden |
| Koppeling inventory-event naar bronregel | `inventory_events.source_reference` + `source_line_id` | behouden |
| Actuele voorraad | `inventory` projectie / temporal inventory reconciliation | behouden |
| Receipt verwijderd in oude implementatie | `receipt_tables.deleted_at`, `raw_receipts.deleted_at` | betekenis is historisch ambigu; niet achteraf als archive/remove interpreteren |

## 3. Vastgestelde problemen in huidige cyclus

### 3.1 Kassa-delete draait nu voorraad terug

De huidige `/api/receipts/delete` roept `remove_receipt_inventory_events()` aan voordat de receipt soft-deleted wordt. Daardoor betekent de bestaande knop technisch óók: verwijder reeds opgeborgen inventory-events en reconcilieer voorraad.

Dat is niet het nieuwe functionele contract. In Release B moet workflow-delete worden losgekoppeld van expliciete inventory reversal.

### 3.2 Reimport wordt nu mogelijk gemaakt door bronhash te muteren

Bij huidige delete wordt `raw_receipts.sha256_hash` aangepast met een `:deleted:` suffix. Daarmee wordt de originele bronidentiteit vernietigd om de unieke index te omzeilen.

Release A wijzigt de index naar unieke actieve bronnen (`WHERE deleted_at IS NULL`). Daardoor kan Release B de originele hash behouden en een exact verwijderde bron opnieuw toelaten zonder identiteitsdata te verminken.

### 3.3 Uitpakken is import-id-gebaseerd

Receiptregels worden nu naar `purchase_import_lines.external_line_ref` vertaald als `receipt-line:<receipt_table_line.id>`. Dit is correct voor één importpoging maar onvoldoende om dezelfde fysieke aankoopregel over een herimport te herkennen.

Release A voegt daarom een stabiele logische sleutel toe aan de bestaande receiptregel in plaats van een nieuwe identitytabel.

### 3.4 Bonstatus alleen is onvoldoende

`receipt_tables.approved_at`/`parse_status` beschrijven de bon op hoofdniveau. Voor gedeeltelijke verwerking is de bestaande regelstatus (`is_validated`) en Uitpakken-/inventoryhistorie leidend. Geen nieuwe globale `processed`-flag wordt toegevoegd.

## 4. Minimale database-delta

Release A voegt exact drie persistente velden toe:

### `receipt_tables.logical_receipt_key`

Opaque stabiele businessidentiteit voor dezelfde fysieke/logische bon over meerdere importpogingen. Bestaande bonnen krijgen een eenmalige UUID-key. Een latere reconciliationservice mag dezelfde key aan een herimport toekennen.

Dit veld bevat geen kopie van winkel, datum, bedrag of hash.

### `receipt_table_lines.logical_line_key`

Opaque stabiele businessidentiteit voor dezelfde fysieke aankoopregel over meerdere importpogingen. Bestaande regels krijgen een eenmalige UUID-key. Een latere reconciliationservice mag dezelfde key hergebruiken.

Het veld is bewust **niet uniek**: meerdere technische importregels mogen dezelfde logische aankoopregel representeren.

### `receipt_tables.workflow_state`

Bevat uitsluitend de disposition van de receipt in de workflow, niet de approval- of inventorystatus.

Voorziene waarden:

- `active`
- `archived`
- `returned_to_kassa`
- `removed_reimport_allowed`
- `legacy_deleted`

Bestaande rows met `deleted_at` krijgen `legacy_deleted`, omdat Release A niet retrospectief mag verzinnen of de gebruiker ooit archiveerde of verwijderde.

## 5. Geen nieuwe tabellen

Release A maakt geen nieuwe datatabel aan. Dit is een expliciete regressie-eis en wordt geautomatiseerd getest.

Niet toegevoegd:

- `receipt_identities`
- `receipt_line_identities`
- `receipt_line_processing`
- `archived_receipts`
- `receipt_inventory_history`

## 6. Afgeleide status in toekomstige releases

De latere Kassa-/Uitpakkenstatus wordt berekend uit bestaande bronnen.

Conceptueel:

- geen Uitpakken-record en geen inventory-event -> nieuw/beschikbaar;
- relevante bestaande Uitpakken-regel, nog geen inventory-event -> eerder goedgekeurd / in Uitpakken;
- oude Uitpakken-flow verwijderd en geen inventory-event -> opnieuw beschikbaar volgens workflowregel;
- inventory-event gekoppeld -> eerder opgeborgen, nooit opnieuw voorraad toevoegen.

Deze labels worden niet als duplicaatstatus opgeslagen als ze uit de canonieke feiten kunnen worden bepaald.

## 7. Inventory-invariant

Voor één fysieke/logische aankoopregel mag gedurende delete/archive/restore/reimport maximaal één effectieve purchase-voorraadmutatie bestaan, tenzij een afzonderlijke expliciete reversal/correctiehandeling wordt uitgevoerd.

`inventory_events` blijft hiervoor de enige ledger.

## 8. Release A code

Nieuwe service:

`backend/app/services/receipt_lifecycle_foundation_service.py`

Verantwoordelijkheden:

- schema idempotent uitbreiden;
- bestaande bonnen en regels éénmalig een opaque logical key geven;
- oude deleted rows als `legacy_deleted` markeren zonder semantiek te verzinnen;
- active-only uniqueness voor `raw_receipts.sha256_hash` installeren;
- geen gebruikersflow wijzigen.

Startupregistratie:

`backend/app/__init__.py`

ORM/documentatiemodel:

`backend/app/models/receipt.py`

## 9. Release A regressie

Testbestand:

`backend/tests/test_receipt_lifecycle_foundation.py`

Permanente CI-gate:

`.github/workflows/receipt-lifecycle-foundation.yml`

De test bewijst minimaal:

1. Release A maakt geen parallelle datatabellen.
2. Alleen de drie afgesproken velden worden toegevoegd.
3. Backfill is idempotent; bestaande logical keys veranderen niet.
4. Logical receipt/line keys mogen over herimports worden hergebruikt.
5. Dezelfde actieve bronhash blijft geblokkeerd.
6. Dezelfde bronhash mag opnieuw bestaan nadat de vorige raw receipt soft-deleted is.
7. Oude verwijderingen krijgen geen verzonnen archive/remove-betekenis.

## 10. Bewust nog niet in Release A

Release A verandert nog niet:

- `/api/receipts/delete`;
- Kassa-delete UI;
- herimport reconciliation;
- Uitpakken delete/return/archive UI;
- archief herstellen;
- daadwerkelijke koppeling van nieuwe imports aan bestaande logical keys;
- inventory reversal UX.

Die gedragswijzigingen starten pas nadat deze fundering groen is.

## 11. Volgende stap na groene Release A foundation

Release B kan vervolgens veilig de Kassa-delete en herimportflow wijzigen:

- gewone delete verwijdert geen inventory-events meer;
- bronhash blijft ongewijzigd;
- workflow_state wordt `removed_reimport_allowed`;
- herimport zoekt de eerdere logical receipt en reconcilieert regels;
- eerder opgeborgen regels worden read-only geblokkeerd;
- nog niet definitief verwerkte regels worden opnieuw beschikbaar volgens hun canonieke Uitpakken-/inventorystatus.
