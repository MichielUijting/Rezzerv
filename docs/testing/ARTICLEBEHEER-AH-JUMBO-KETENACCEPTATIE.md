# Artikelbeheer: AH/Jumbo-ketenacceptatie (issue #652)

Status: gerichte, synthetische PostgreSQL-integratieproef voor issue #652; geen productie- of PO-datamutatie.

## Doel en normatieve grenzen
Verifieer de keten **bonartikel/ED2-identificatie → centrale Catalogus → GS1 en CBS → expliciete synoniemen → Bijna op** zonder product-, bon- of huishoudidentiteiten samen te voegen.

- Twee afzonderlijke Catalogusproducten: AH halfvolle melk en Jumbo halfvolle melk, elk **1 liter**, met verschillende bevestigde GTIN's en winkelgebonden artikelcodes. De positieve synoniemproef gebruikt dus gelijke fysieke verpakkingsinhoud; uiteenlopende formaten worden niet zonder extra bewijs als gelijkwaardig geaccepteerd.
- Een bevestigde ED2-koppeling blijft gekoppeld aan de correcte centrale `global_product_id`; verschillende winkelcodes en GTIN's blijven onderscheiden.
- **GS1 GPC en CBS zijn twee officiële classificatieautoriteiten.** Alleen ontbrekende classificaties worden na expliciete synoniembevestiging transactioneel overgenomen. Verschillen worden nooit stil overschreven; de bestaande A–B–C-test op elke PR controleert de keuze-overlay en afzonderlijke keuzes.
- De bestaande groepslogica van Bijna op mag samenvatten als de actuele GS1-/groepsautoriteiten daarvoor voldoende zijn, maar mag daardoor geen nieuwe voorraadmutatie, gebeurtenis of extra huishoudartikel creëren.
- Huishoudartikel-, voorraad-, kassabon- en artikelidentiteit blijven afzonderlijk. Synoniemen vormen geen nieuwe aankoop en creëren geen ontvangsten.
- Het verwijderen van noodzakelijke GS1-/groepsinformatie mag niet door een oud synoniem worden omzeild: de Bijna op-presentatie moet dan weer gescheiden zijn.

## Geautomatiseerd bewijs op een *geïsoleerde* PostgreSQL-testdatabase

Bestaande test `StoreTest.test_ed2_catalog_synonyms_almost_out_cross_store_chain` in `backend/tests/test_article_synonyms.py` is uitgebreid met:

1. Twee synthetische bonnen staan in de canonieke PostgreSQL-tabellen `raw_receipts`, `receipt_tables` en `receipt_table_lines`. De **echte ED2-bronquery** haalt hun bonregels op (inclusief rol- en eligibilityfilters), waarna ED2 precies de AH- en Jumbo-bonartikelen projecteert met verschillende bevestigde artikelcodes/GTIN's en juiste centrale product-ID's.
2. Catalogus bevat twee producten; beide hebben de afzonderlijk vastgelegde GS1-brick. CBS heeft vóór koppeling uitsluitend een expliciete bevestiging voor AH.
3. Bijna op projecteert vóór koppeling de GS1-gebaseerde groep met twee afzonderlijke `household_article_id`'s en een onveranderde voorraadhoeveelheid.
4. De productkoppeling wordt uitsluitend op een actuele serverfingerprint expliciet bevestigd; Jumbo erft daarna CBS van AH, maar er ontstaat **geen tweede GS1-overname** omdat de GS1-classificatie al gelijk is.
5. De append-only audit verwijst naar `source_product_id=a`, `target_product_id=b`, officiële CBS-code en status `processed`. Een herhaalde bevestiging maakt geen tweede CBS-historieregel of auditregel.
6. Catalogus vermeldt de directe winkelrelaties zonder identiteiten samen te voegen. Bijna op blijft de twee huishoudartikelen in huishouden A en hun voorraadregistraties tonen; geen nieuwe `inventory_events` of bonartikelrelaties. Een tweede huishouden bezit zelfstandig hetzelfde centrale product met een andere huishoudartikel-ID en voorraadhoeveelheid. Beide projecten filteren expliciet op huishouden, ook wanneer de aanroeper bewust een vreemde huishoudartikel-ID meestuurt; die vreemde ID levert geen zichtbare voorraad op.
7. Na het bewust wegnemen van GS1-/groepsbewijs in de **testdatabase** mogen ED2 en Bijna op geen gelijkwaardigheid suggereren op basis van een synoniem alleen.

Deze test gebruikt een per-test tijdelijk PostgreSQL-schema; alle bonnen, producten, classificaties, huishoudartikelen en voorraadregels zijn synthetisch. De echte `_source_articles`-selectie, ED2-projectie, Catalogusprojectie, synoniem- en classificatietransacties en Bijna op-groepering worden aangeroepen. De test voert **geen** retailer-login, OCR, scanner, daadwerkelijke ontvangst of Kassa-goedkeuring uit.

## Gerichte runtimefout en reparatie

De echte PostgreSQL-query liet een eerder verborgen typefout zien: `receipt_table_lines.inventory_eligible = 1` vergelijkt een boolean met een integer. De productieservice is gecorrigeerd naar de PostgreSQL- én SQLite-veilige voorwaarde `inventory_eligible IS TRUE`. De opnieuw uitgevoerde PostgreSQL-ketentest bevestigt dat de canonieke bonbron nu werkt. De reparatie wijzigt geen schema, bon, voorraad of gebruikersdata.

## Grenzen die NIET met dit bewijs mogen worden geclaimd

- Geen echte AH/Jumbo-login, digitale bonimport, OCR, daadwerkelijke ontvangst, Kassa-goedkeuring, Uitpakken of retailernetwerkkoppeling. **Het selecteren van bestaande bonregels uit het canonieke receipt-schema is wél echt getest**.
- Geen echte front-end doorloop door één gebruiker van alle drie Artikelbeheerwerkgebieden in dezelfde browsersessie.
- Geen volledige geautoriseerde productie-API-keten of daadwerkelijk via de reguliere gebruikersroute aangemaakte huishoudens; de nieuwe test bewijst gerichte huishoudfiltering van de **echte Bijna op-dataprojectie** met twee synthetische huishoudens, maar geen volledige authenticatie- en rolautorizatie. Die eisen blijven onderbouwd door de bestaande afzonderlijke huishouden-, voorraad-, kassabon- en autorisatieregressies.
- Geen bewijs dat synoniemen zonder voldoende GS1-/productgroepinformatie automatisch in Bijna op gegroepeerd mogen worden.

## Acceptatie en resterende praktijktoets

De gerichte PostgreSQL-ketentest, de bestaande elke-PR A–B–C-autoriteit en de frontend-overlaycontracten zijn verplichte automatische basis. De volledige fysieke pilotroute vanaf een **werkelijk geïmporteerde** AH/Jumbo-bon via Kassa/Uitpakken tot Bijna op blijft een afzonderlijke functionele PO-praktijktoets op een veilige testomgeving; deze PR claimt die niet. Huishoudautorisatie wordt ook door bestaande specifieke runtime-/rolregressies bewaakt, niet vervangen door synthetische fixturedata. UI-sanering, OFF-uitbreidingen en algemene herontwerpen blijven buiten deze PR. Vóór Ready gelden definitieve versie/versiesync en preflightchecks; F7 draait uitsluitend op de finale SHA. **Nooit merge of deploy zonder afzonderlijke PO-GO.**
