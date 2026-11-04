# Inhuis — interne GS1/CBS-synoniemensynchronisatie en uitzonderingsaudit (#649)

Status: technisch contract voor PR #651. Geldig vanaf de nieuwe Alembic-schemahead; geen automatische historisch-datamigratie of backfill.

## Schrijf- en identity-autoriteit
- Alleen een reeds expliciet bevestigd synoniemverband tussen canonieke `global_products.id` kan tot classificatieovername leiden. Een bonregel, huishouden, productnaam, zoekscore, gelijke classificatie of winkelcode is daarvoor geen toestemming.
- De bestaande `confirm_pairs`-transactie, `global_product_gpc_bricks`, `global_product_cbs_classifications`, `global_product_cbs_history` en officiële CBS-eindcategoriecontrole blijven leidend. Het synoniemenverband wordt onder één PostgreSQL advisory lock bevestigd en verwerkt.
- Een bestaande ongelijke classificatie wordt nooit automatisch overschreven. De al beschikbare keuze-overlay **Artikel-synoniemen** vraagt voor GS1 en CBS afzonderlijk om een expliciete prevalentie, inclusief naam en officiële code.
- Overname naar een nog niet geclassificeerd product en de bijbehorende auditregel zijn atomair. Een technische fout rolt beide terug. Geen voorraaddata, bonnen of huishoudartikelen worden bijgewerkt.

## Append-only eventbewijs
`article_classification_sync_events` bevat: UUID, stabiele idempotentiesleutel, bron- en doel-`global_product_id`, systeem GS1 GPC/CBS, officiële code en referentie, beslisversie, status, reden, actor/systeemoorsprong en aanmaaktijd. Een optionele `related_event_id` koppelt een later geslaagd retry- of prevalentie-event aan een eerdere uitzondering, zonder historie te wissen of te overschrijven.

Geldige toestanden: `pending` (expliciete retry in transactie), `processed` (overgenomen of expliciet gekozen), `conflict` (verschillende bevestigde classificaties), `review_required` (onvoldoende officiële referentiebewijs), `failed` (mislukte verwerkingspoging indien deze ná rollback afzonderlijk veilig wordt geregistreerd). Het ontbreken van een logregel uit het verleden mag nooit als nul historische conflicten worden geïnterpreteerd.

Event-sleutels bevatten de canonieke identiteit, systeem, code, referentie, versie, status en operatie; gelijkwaardige retries kunnen geen identieke auditregels toevoegen. De actieve monitor telt **auditgebeurtenissen**, niet bonnen, huishoudproducten, synoniempaar-suggesties of hoeveelheden.

## Interne endpoints en uitzonderingen
- `GET /api/external-databases/article-synonyms/sync-exceptions`: alleen-lezen interne lijst voor geautoriseerde Superuser/Frontteamcontext; resoluties verwijderen geen geschiedenis, maar verbergen aantoonbaar afgehandelde uitzonderingen uit de actieve lijst.
- `POST /api/external-databases/article-synonyms/sync-exceptions/retry`: aparte expliciete, sessie-geautoriseerde transactie; vereist event-ID, beslisversie, verwachte actuele doelversie én doelcode. Bij GS1 is ook `gpc.update` nodig. Geen achtergrondbatch of muterende GET.
- De retry controleert actieve centrale producten, de nog bestaande bevestigde synoniemketen en actuele bron-/doelwaarden. Bij stale snapshots, ontbrekende referentie of inhoudelijk classificatieconflict stopt hij met 409 en rollback; conflicten lopen uitsluitend via de bestaande keuze-overlay.
- Er komt **geen** reguliere knop of vierde werkgebied *Synchroniseren*.

## Tests
Geïsoleerde PostgreSQL-artikelsynoniemtests behandelen twee onafhankelijke officiële indelingen, bron/doel, transactierollback, idempotentie, stale versies, conflicten, veilige retry en rechten 401/403. Bestaande mobiele/desktop-Playwrighttests blijven van kracht. De nieuwe migratie is additief, gebruikt de PostgreSQL-onderhoudsbarrière en weigert downgrade zolang auditgegevens bestaan.

De audit weerspiegelt alleen gebeurtenissen **vanaf** de invoering ervan. Het bestaande classificatiearchief wordt niet stilzwijgend gehistoriseerd of geclassificeerd.
