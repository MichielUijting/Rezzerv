# Artikelbeheer: AH/Jumbo-ketenacceptatie (issue #652)

Status: eerste gerichte PostgreSQL-integratieproef in Draft PR, geen productie- of PO-datamutatie.

## Doel en normatieve grenzen
Verifieer de keten **bonartikel/ED2-identificatie → centrale Catalogus → GS1 en CBS → expliciete synoniemen → Bijna op** zonder product-, bon- of huishoudidentiteiten samen te voegen.

- Twee afzonderlijke Catalogusproducten: AH halfvolle melk en Jumbo halfvolle melk, verschillende bevestigde GTIN's en winkelgebonden artikelcodes.
- Een bevestigde ED2-koppeling blijft gekoppeld aan de correcte centrale `global_product_id`; verschillende winkelcodes en GTIN's blijven onderscheiden.
- **GS1 GPC en CBS zijn twee officiële classificatieautoriteiten.** Alleen ontbrekende classificaties worden na expliciete synoniembevestiging transactioneel overgenomen. Verschillen worden nooit stil overschreven; de bestaande A–B–C-test op elke PR controleert de keuze-overlay en afzonderlijke keuzes.
- De bestaande groepslogica van Bijna op mag samenvatten als de actuele GS1-/groepsautoriteiten daarvoor voldoende zijn, maar mag daardoor geen nieuwe voorraadmutatie, gebeurtenis of extra huishoudartikel creëren.
- Huishoudartikel-, voorraad-, kassabon- en artikelidentiteit blijven afzonderlijk. Synoniemen vormen geen nieuwe aankoop en creëren geen ontvangsten.
- Het verwijderen van noodzakelijke GS1-/groepsinformatie mag niet door een oud synoniem worden omzeild: de Bijna op-presentatie moet dan weer gescheiden zijn.

## Geautomatiseerd bewijs op een *geïsoleerde* PostgreSQL-testdatabase

Bestaande test `StoreTest.test_ed2_catalog_synonyms_almost_out_cross_store_chain` in `backend/tests/test_article_synonyms.py` is uitgebreid met:

1. ED2 projecteert precies AH- en Jumbo-bonartikelen met verschillende bevestigde artikelcodes/GTIN's en de juiste centrale product-ID.
2. Catalogus bevat twee producten; beide hebben de afzonderlijk vastgelegde GS1-brick. CBS heeft vóór koppeling uitsluitend een expliciete bevestiging voor AH.
3. Bijna op projecteert vóór koppeling de GS1-gebaseerde groep met twee afzonderlijke `household_article_id`'s en een onveranderde voorraadhoeveelheid.
4. De productkoppeling wordt uitsluitend op een actuele serverfingerprint expliciet bevestigd; Jumbo erft daarna CBS van AH, maar er ontstaat **geen tweede GS1-overname** omdat de GS1-classificatie al gelijk is.
5. De append-only audit verwijst naar `source_product_id=a`, `target_product_id=b`, officiële CBS-code en status `processed`. Een herhaalde bevestiging maakt geen tweede CBS-historieregel of auditregel.
6. Catalogus vermeldt de directe winkelrelaties zonder identiteiten samen te voegen. Bijna op blijft dezelfde twee huishoudartikelen en voorraadregistraties tonen; geen nieuwe `inventory_events` of bonartikelrelaties.
7. Na het bewust wegnemen van GS1-/groepsbewijs in de **testdatabase** mogen ED2 en Bijna op geen gelijkwaardigheid suggereren op basis van een synoniem alleen.

Deze test gebruikt een per-test tijdelijk PostgreSQL-schema; alle data zijn synthetisch. De `_source_articles`-adapter die oorspronkelijke bonregels aanlevert is bewust gestubd. De resterende ED2-projectie, Catalogusprojectie, synoniem- en classificatietransacties en Bijna op-groepering zijn echte backendroutes/services.

## Grenzen die NIET met dit bewijs mogen worden geclaimd

- Geen volledige echte AH/Jumbo-login, digitale bonimport, OCR, daadwerkelijke bonverwerking of retailernetwerkkoppeling.
- Geen echte front-end doorloop door één gebruiker van alle drie Artikelbeheerwerkgebieden in dezelfde browsersessie.
- Geen volledige geautoriseerde productie-API-keten of daadwerkelijk aangemaakte huishoudens; de huishoudisolatie-eisen moeten verder worden onderbouwd met de bestaande speciale huishouden-, voorraad-, kassabon- en autorisatieregessies.
- Geen bewijs dat synoniemen zonder voldoende GS1-/productgroepinformatie automatisch in Bijna op gegroepeerd mogen worden.

## Vervolgacceptatie vóór Ready

Controleer de gerichte PostgreSQL-test en de bestaande elke-PR A–B–C-autoriteit. Inspecteer de actuele frontend en API voor ontbrekende overgangen en voeg alleen werkelijk noodzakelijke contracttests/reparaties binnen issue #652 toe. Houd UI-sanering, OFF-uitbreidingen en algemene herontwerpen buiten scope. Voor Ready gelden definitieve versiesync, normale/preflightchecks en F7 op de finale SHA. **Nooit merge of deploy zonder afzonderlijke PO-GO.**
