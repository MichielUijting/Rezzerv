# Ketentest: twee winkels, ED2 → Catalogus → Artikelsynoniemen → Bijna op

**Status:** uitvoerbare, geïsoleerde PostgreSQL-ketenacceptatie.
**TEST_LEVEL_PROVISIONAL: M.**

> **Scope na PO-besluit van 3 november 2026 (PR #644, inmiddels op main):** GPC en CBS blijven beide bestaan. Deze PR #639 is uitsluitend een **regressiebaseline van de bestaande keten**; hij implementeert of valideert nog **geen** automatische overname van GPC/CBS bij bevestigde synoniemen. In de eerstvolgende functionele implementatie-PR moeten aanvullende ketentests bewijzen: overname GPC én CBS in beide richtingen, overname binnen bevestigde synoniemgroepen, idempotente herhaling, behoud van bestaande afwijkende bevestigde waarden, transactierollback en provenance/audit. De negatieve test hieronder is een bewust vastgelegd **huidig runtimegedrag**, geen blijvende eis dat GPC ontbrekend blijft nadat de toekomstige overnameservice is ingevoerd. Na die implementatie moet deze baseline opnieuw op het nieuwe contract worden beoordeeld, niet stilzwijgend als norm gebruikt.


## Concrete proef
- Artikel A: **AH Halfvolle melk**, AH-bonartikelcode `823326`, GTIN `8719587325926`, inhoud 1 liter.
- Artikel B: **Jumbo Halfvolle melk**, Jumbo-bonartikelcode `394270`, GTIN `8718452513666`, inhoud 500 ml.
- Beide artikelen krijgen voor de positieve proef de bestaande officiële GS1 GPC Brick `10000025`, maar blijven afzonderlijke Catalogusproducten en bonartikelidentiteiten.
- Een geïsoleerd proefhuishouden heeft één verpakking van A en twee verpakkingen van B, samen 2 liter. Geen werkelijke gebruikersbon of voorraad wordt geraakt.

## Verwachte ketenuitkomst
1. **ED2** leest twee afzonderlijke, server-bevestigde winkelartikelkoppelingen. Elke boncode en GTIN blijft bij de juiste winkel en het juiste Catalogusproduct. De ED2-resolver en volledigheidscontrole draaien echt; uitsluitend de herkomst van de twee bonregels is testdata.
2. **Catalogus** heeft vóór bevestiging nul gekoppelde andere winkels. De bestaande synoniemensuggesties presenteren het AH/Jumbo-paar. Bevestiging is expliciet, atomair en idempotent. Vervolgens toont Catalogus bij beide producten één direct gekoppelde andere winkel; GTIN en productidentiteit blijven verschillend.
3. **Bijna op** gebruikt de bestaande producttype- en verpakkingslogica om 1 liter plus tweemaal 500 ml als 2 liter in één uitlegbaar producttype te projecteren, met beide oorspronkelijke huishoudartikelen. De opgeslagen inventarisaantallen blijven 1 en 2; geen inventory event wordt aangemaakt.
4. **Negatieve proef:** verwijder alleen in het geïsoleerde testschema de GS1-toekenning bij Jumbo. De bevestigde synoniemenrelatie blijft bestaan maar ED2 mag de onvolledige exacte koppeling niet meer als operationeel bevestigd tonen. Bijna op mag zonder bruikbare producttypegegevens de twee artikelen niet automatisch samenvoegen. Geen echte gebruiksdata worden gewijzigd.

## Wat deze test wel en niet bewijst
De test draait in de al bestaande, door `INHUIS_ARTICLE_SYNONYMS_TEST_DATABASE_URL` afgeschermde PostgreSQL-omgeving. Elke testcase gebruikt een uniek tijdelijk schema dat na afloop wordt verwijderd. De bestaande workflow **Article synonyms validation** voert `backend/tests/test_article_synonyms.py` uit, inclusief deze ketentest.

Deze backendtest verifieert de daadwerkelijke ED2-presentatie-/resolverservices, Catalogusprojectie, synoniemenopslag en Bijna op-groepering. Hij simuleert **niet** een echte kassabonscan, de volledige gebruikersinterface of een daadwerkelijke aanvulling op de boodschappenlijst. Die zijn aparte end-to-end acceptatiepunten.

**Belangrijke functionele grens:** `article_synonym_links` is momenteel **geen rechtstreeks invoersignaal** voor `almost_out_group_service`. Het veilig samenvoegen in Bijna op werkt via bruikbare GS1/producttype- en inhoudsinformatie. Een expliciet bevestigd synoniem met ontbrekende classificatie wordt daarom niet automatisch gegroepeerd. Dit is een geobserveerde ontwerpgrens, niet iets wat de test als volledig geïmplementeerde synoniemenpropagatie mag presenteren.

Geen applicatiegedrag, databasecontract, CI-orchestratie of gebruikersdata wijzigen; uitsluitend test en documentatie.
