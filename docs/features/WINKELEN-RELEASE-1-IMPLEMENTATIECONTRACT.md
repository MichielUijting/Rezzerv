# Winkelen — Release 1 implementatiecontract

Datum: 2026-08-02
Status: DRAFT / ontwikkeling
Branch: `feature/winkelen-release-1`

## Doel

Release 1 levert één zelfstandige actieve winkellijst per huishouden. De lijst start leeg. De gebruiker zoekt eerst een kandidaat in de Rezzerv-catalogus, voegt deze toe en vult daarna alleen waar nodig aanvullende gegevens in de tabel aan. Release 1 bevat nog geen push vanuit Bijna op of Gerechten.

## Functionele scope

1. Nieuw scherm `/winkelen` volgens de standaard Rezzerv-UI.
2. Eén actieve winkellijst per huishouden.
3. Een lege lijst toont de Rezzerv-empty-state.
4. Boven de tabel staat één full-text zoekfunctie met de zoekscopes:
   - Huishoudartikelen;
   - Producttypen;
   - Artikelgroepen.
5. De gebruiker selecteert één zoekresultaat en voegt dit met `Toevoegen` aan de winkellijst toe.
6. Aantal, volume, eenheid en opmerking zijn niet verplicht bij toevoegen.
7. Deze aanvullende gegevens zijn daarna inline in de tabel wijzigbaar.
8. Een regel kan als gekocht worden afgevinkt.
9. `Winkelen afgerond` vraagt bevestiging en maakt daarna de actieve tabel leeg.
10. Afronden wijzigt Voorraad, Bijna op, Gerechten en kassabonnen niet.
11. Data van andere huishoudens is nooit zichtbaar of wijzigbaar.

## Expliciet verwijderd uit het scherm

- de eerste invoerregel met Artikel, Aantal, Volume, Eenheid en Opmerking;
- de kolom `Actie`;
- de regelactie `Verwijderen`;
- de knop `Afsluiten`.

## Buiten scope

- toevoegen vanuit Bijna op;
- toevoegen vanuit Gerechten;
- automatisch samenvoegen van kandidaatartikelen;
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

- `GET /api/shopping-list/catalog-search?scope={scope}&query={query}`

Ondersteunde scopes:

- `household_articles`
- `product_types`
- `article_groups`

De zoekactie gebruikt uitsluitend het huishouden uit de server-side sessie. Huishoudartikelen en Artikelgroepen hergebruiken de bestaande Rezzerv-projecties. Producttypen worden uit de centrale producttype-/productgroepcatalogus geprojecteerd.

Een zoekresultaat bevat minimaal:

- `source_type`
- `source_id`
- `label`
- `article_name`
- `article_group_name`
- `product_type_name`

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

1. dropdown `Zoeken in`;
2. full-text veld `Catalogus zoeken`;
3. dropdown `Zoekresultaat`;
4. knop `Toevoegen`.

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

Standaardgedrag:

- numerieke waarden rechts uitgelijnd;
- donkergroene checkbox;
- Aantal, Volume, Eenheid en Opmerking inline wijzigbaar;
- kolombreedtes handmatig verstelbaar;
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
2. Full-text zoeken werkt voor alle drie scopes.
3. Alleen een geselecteerd catalogusresultaat kan worden toegevoegd.
4. Toevoegen vereist geen aantal, volume, eenheid of opmerking.
5. Toegevoegde regels blijven na herladen bestaan.
6. Inline aanvullingen blijven na herladen bestaan.
7. Afvinken blijft na herladen bewaard.
8. Zoek- en filterregel werkt op de actieve tabel.
9. Kolombreedtes zijn verstelbaar.
10. Kolom Actie en knop Afsluiten zijn afwezig.
11. Afronden maakt de actieve weergave leeg.
12. Afronden wijzigt Voorraad niet.
13. Een gebruiker kan nooit regels van een ander huishouden lezen of muteren.
14. Backend- en frontendbuild zijn groen.
15. Volledige regressie en productie-ketentest zijn groen op de actuele head.

## Releasegate

De eerdere groene resultaten van head `b922d2bbab514f1363f601e763364c961af382c5` gelden niet als vrijgave voor deze gewijzigde schermversie.

Geen merge, release of deployment zonder:

- groene backend-selftest op de actuele head;
- groene frontendbuild;
- volledige bestaande frontendregressie groen;
- aangepaste Winkelen-regressie groen;
- productie-ketentest 12/12 groen;
- gecontroleerde huishoudisolatie;
- functionele PO-controle;
- QA/QC GO;
- expliciete PO-GO.
