# Winkelen — Release 1 implementatiecontract

Datum: 2026-08-02
Status: DRAFT / ontwikkeling
Branch: `feature/winkelen-release-1`

## Doel

Release 1 levert één zelfstandige actieve winkellijst per huishouden. De lijst start leeg. De gebruiker zoekt met één zoekveld tegelijk in alle relevante Rezzerv-catalogusbronnen, kiest een kandidaat, voegt deze toe en vult daarna alleen waar nodig aanvullende gegevens in de tabel aan. Release 1 bevat nog geen push vanuit Bijna op of Gerechten.

## Functionele scope

1. Nieuw scherm `/winkelen` volgens de standaard Rezzerv-UI.
2. Eén actieve winkellijst per huishouden.
3. Een lege lijst toont de Rezzerv-empty-state.
4. Boven de tabel staat één full-text zoekveld dat gelijktijdig zoekt in Huishoudartikelen, Producttypen en Artikelgroepen.
5. De keuzelijst `Zoeken in` is niet aanwezig.
6. Zoekresultaten worden per bron gegroepeerd en dragen een herkenbaar bronlabel.
7. De gebruiker selecteert één zoekresultaat en voegt dit met `Toevoegen` aan de winkellijst toe.
8. Aantal, volume, eenheid en opmerking zijn niet verplicht bij toevoegen.
9. Deze aanvullende gegevens zijn daarna inline in de tabel wijzigbaar.
10. Een regel kan als gekocht worden afgevinkt.
11. `Winkelen afgerond` vraagt bevestiging en maakt daarna de actieve tabel leeg.
12. Afronden wijzigt Voorraad, Bijna op, Gerechten en kassabonnen niet.
13. Data van andere huishoudens is nooit zichtbaar of wijzigbaar.

## Expliciet verwijderd uit het scherm

- de eerste invoerregel met Artikel, Aantal, Volume, Eenheid en Opmerking;
- de dropdown `Zoeken in`;
- de kolom `Actie`;
- de regelactie `Verwijderen`;
- de knop `Afsluiten`.

## Buiten scope

- toevoegen vanuit Bijna op;
- toevoegen vanuit Gerechten;
- samenvoegen van verschillende catalogusidentiteiten uitsluitend op basis van gelijke naam;
- voorraadmutatie vanuit Winkelen;
- kassabonkoppeling;
- winkelgroepering;
- offline synchronisatie.

## Datamodel

### `shopping_lists`

- `id`
- `household_id`
- `status` (`active` of `completed`)
- `created_at`
- `completed_at`
- `completed_by`

Contract: maximaal één actieve lijst per huishouden.

### `shopping_list_items`

- `id`
- `shopping_list_id`
- `household_id`
- `article_name`
- `article_group_name`
- `product_type_name`
- `source_type`
- `source_id`
- `quantity`
- `volume`
- `unit`
- `note`
- `checked`
- `created_at`
- `updated_at`

Bestaande lokale databases worden additief uitgebreid; bestaande winkellijstregels blijven geldig.

## Cataloguszoekcontract

Endpoint:

- `GET /api/shopping-list/catalog-search?scope=all&query={query}`

De gecombineerde zoekactie gebruikt uitsluitend het huishouden uit de server-side sessie en doorzoekt:

- `household_articles` via de bestaande huishoudartikelprojectie;
- `product_types` via de centrale producttype-/productgroepcatalogus;
- `article_groups` via de bestaande artikelgroepprojectie.

De route retourneert:

- één gecombineerde lijst `items`;
- totaal `total`;
- aantallen per brontype in `counts`.

Een zoekresultaat bevat minimaal:

- `source_type`
- `source_id`
- `label`
- `article_name`
- `article_group_name`
- `product_type_name`

Rangschikking:

1. exacte overeenkomst;
2. begint met zoekterm;
3. bevat zoekterm;
4. bij gelijke relevantie: Huishoudartikel, Producttype, Artikelgroep;
5. daarna alfabetisch.

Gelijke labels uit verschillende bronnen blijven afzonderlijke resultaten, omdat hun bronidentiteit en betekenis verschillen.

## Overig API-contract

- `GET /api/shopping-list`
- `POST /api/shopping-list/items`
- `PUT /api/shopping-list/items/{item_id}`
- `DELETE /api/shopping-list/items/{item_id}` blijft technisch beschikbaar, maar heeft in Release 1 geen zichtbare schermactie
- `POST /api/shopping-list/complete`

Alle endpoints gebruiken uitsluitend het actieve server-side sessiehuishouden. Een `household_id` uit de browser mag de sessiecontext niet overschrijven.

## Autorisatie

Bestaande permissies:

- `shopping_list.view`
- `shopping_list.update`
- `shopping_list.manage`

De volledige centrale autorisatiematrix geldt, inclusief individuele `allow`- en `deny`-uitzonderingen.

## UI-contract

Schermtitel: `Winkelen`

Boven de tabel:

1. full-text veld `Catalogus zoeken`;
2. gegroepeerde dropdown `Zoekresultaat` met bronlabels;
3. knop `Toevoegen`;
4. compacte aantallen per bron.

Tabelkolommen:

1. Gekocht
2. Artikel
3. Artikelgroep
4. Producttype
5. Aantal
6. Volume
7. Eenheid
8. Opmerking

Onder de kolomkoppen staat de standaard zoek- en filterregel:

- Gekocht: Filter / Nog te kopen / Gekocht;
- Artikel: `Zoeken`;
- Artikelgroep: `Filter`;
- Producttype: `Filter`;
- Eenheid: `Filter`.

### Vaste tabelgeometrie

- de tabel gebruikt `table-layout: fixed`;
- de totale initiële tabelbreedte is vast en verandert niet door zoekresultaten, toegevoegde waarden of celinhoud;
- de initiële kolombreedtes zijn vastgelegd via `colgroup`;
- lange waarden mogen de tabel niet verbreden;
- volledige tekst blijft beschikbaar via de celtooltip;
- bij onvoldoende schermruimte wordt horizontaal gescrold;
- kolommen blijven handmatig verstelbaar;
- een handmatige resize mag de overige tabelinteractie niet beïnvloeden.

Standaardgedrag:

- numerieke waarden rechts uitgelijnd;
- donkergroene checkbox;
- Aantal, Volume, Eenheid en Opmerking inline wijzigbaar;
- standaard Rezzerv-card en primaire knop;
- geen exitknop op dit scherm;
- `Winkelen afgerond` alleen actief bij een niet-lege lijst.

## Afrondcontract

Na bevestiging:

1. actieve lijst krijgt status `completed`;
2. `completed_at` en `completed_by` worden gevuld;
3. de zichtbare actieve lijst is leeg;
4. een volgende toevoeging gebruikt een nieuwe actieve lijst;
5. geen enkele voorraad- of bronmutatie vindt plaats.

## Acceptatiecriteria

1. Nieuw huishouden opent een lege Winkelen-tabel.
2. Eén zoekopdracht doorzoekt alle drie catalogusbronnen.
3. Resultaten tonen hun bron en zijn per bron gegroepeerd.
4. Alleen een geselecteerd catalogusresultaat kan worden toegevoegd.
5. Toevoegen vereist geen aantal, volume, eenheid of opmerking.
6. Toegevoegde regels blijven na herladen bestaan.
7. Inline aanvullingen blijven na herladen bestaan.
8. Afvinken blijft na herladen bewaard.
9. Zoek- en filterregel werkt op de actieve tabel.
10. De tabelbreedte blijft exact gelijk vóór zoeken, na zoeken en na toevoegen.
11. Kolombreedtes zijn verstelbaar.
12. Dropdown Zoeken in, kolom Actie en knop Afsluiten zijn afwezig.
13. Afronden maakt de actieve weergave leeg.
14. Afronden wijzigt Voorraad niet.
15. Een gebruiker kan nooit regels van een ander huishouden lezen of muteren.
16. Backend- en frontendbuild zijn groen.
17. Volledige regressie en productie-ketentest zijn groen op de actuele head.

## Releasegate

Eerdere groene resultaten gelden niet als vrijgave voor de gewijzigde gecombineerde zoekfunctie en vaste tabelgeometrie.

Geen merge, release of deployment zonder:

- groene backend-selftest op de actuele head;
- groene frontendbuild;
- volledige bestaande frontendregressie groen;
- echte gecombineerde catalogusroute groen;
- tabelbreedteregressie groen;
- productie-ketentest 12/12 groen;
- gecontroleerde huishoudisolatie;
- functionele PO-controle;
- QA/QC GO;
- expliciete PO-GO.


## Aanvullend PO-besluit 2026-09-18

Dit besluit vervangt strijdige eerdere UI- en duplicaatregels in dit document.

- De gebruikerszichtbare naam van de module/lijst is **Boodschappen**. De interne route `/winkelen`, permissies en technische sleutels mogen `winkelen` blijven heten.
- Zoekgestuurde kandidaatselectie toont kandidaten direct zodra de zoekactie resultaten heeft; een extra klik op een gesloten resultaatselectie is niet nodig.
- Er worden maximaal **5 kandidaten** tegelijk getoond. Dit is de applicatiebrede regel voor zoekvelden waarbij de gebruiker één kandidaat uit zoekresultaten kiest; gewone filters en statische keuzelijsten vallen hier niet onder.
- Mobiel en desktop gebruiken voor Boodschappen dezelfde directe kandidaatpresentatie.
- Wanneer dezelfde canonieke kandidaat (`source_type` + `source_id`) opnieuw aan dezelfde actieve boodschappen wordt toegevoegd, ontstaat geen tweede regel. Het bestaande veld **Aantal** wordt verhoogd.
- Voor een eerste canonieke kandidaat zonder expliciet aantal geldt **Aantal = 1**.
- Bestaande duplicaten met dezelfde canonieke kandidaatidentiteit op een actieve lijst worden eenmalig geconsolideerd; aantallen worden daarbij opgeteld. Voltooide/historische lijsten worden niet herschreven.
- Kandidaten met alleen dezelfde zichtbare naam maar een verschillende canonieke bronidentiteit worden niet stilzwijgend samengevoegd.


## Aanvullend PO-besluit 2026-09-25 — mobiele Boodschappen-UI

Dit besluit vervangt strijdige eerdere mobiele UI-regels.

- De gebruikerszichtbare modulenaam is **Boodschappen**; interne technische namen zoals `/winkelen` en `shopping_list` blijven toegestaan.
- Een mobiele artikelregel gebruikt de centrale `MobileArticleRow`, dezelfde regelgeometrie als Voorraad. Nieuwe mobiele artikeloverzichten mogen deze structuur niet lokaal kopiëren.
- De mobiele moduleheader gebruikt `MobileModuleHeader`; de globale mobiele Terug-bediening blijft centraal in `MobileAppChrome` sticky/fixed geregeld.
- Een gebruiker kan naast een cataloguskandidaat ook vrije tekst toevoegen. Zo'n regel krijgt `source_type=manual` en blijft tijdelijk ongestructureerd totdat latere kassabonverwerking de artikelidentiteit structureert.
- De enige checkbox per artikelregel is de koopstatus: aan = in de kar, uit = nog te vinden.
- Boven de koopstatuskolom staat een tweestandenfilter: uit = nog te vinden, aan = in de kar. Standaard worden de nog te vinden artikelen getoond. Een artikel dat in de kar wordt gezet verdwijnt uit die weergave, maar blijft via de aangevinkte filterstand zichtbaar en kan daar weer uit de kar worden gehaald.
- Mobiel heeft geen afzonderlijke Selectie-checkbox en geen actie Bewerken per regel.
- Aantal staat direct in de artikelregel en gebruikt de centrale `QuantityStepper` met min/plus.
