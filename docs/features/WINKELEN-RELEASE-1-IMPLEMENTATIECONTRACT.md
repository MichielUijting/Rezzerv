# Winkelen — Release 1 implementatiecontract

Datum: 2026-08-02
Status: DRAFT / ontwikkeling
Branch: `feature/winkelen-release-1`

## Doel

Release 1 levert een zelfstandige actieve winkellijst per huishouden. De lijst start leeg en ondersteunt handmatig toevoegen, aanpassen, afvinken, verwijderen en afronden. Release 1 bevat nog geen koppeling met Bijna op of Gerechten.

## Functionele scope

1. Nieuw scherm `/winkelen` volgens de standaard Rezzerv-UI.
2. Eén actieve winkellijst per huishouden.
3. Een lege lijst toont de Rezzerv-empty-state.
4. Handmatig toevoegen van een artikel met:
   - artikelnaam;
   - aantal;
   - volume;
   - eenheid;
   - opmerking.
5. Een regel kan als gekocht worden afgevinkt.
6. Een regel kan worden gewijzigd of verwijderd.
7. `Winkelen afgerond` vraagt bevestiging en maakt daarna de actieve tabel leeg.
8. Afronden wijzigt Voorraad, Bijna op, Gerechten en kassabonnen niet.
9. Data van andere huishoudens is nooit zichtbaar of wijzigbaar.

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
- `quantity`
- `volume`
- `unit`
- `note`
- `checked`
- `created_at`
- `updated_at`

## API-contract

- `GET /api/shopping-list`
- `POST /api/shopping-list/items`
- `PUT /api/shopping-list/items/{item_id}`
- `DELETE /api/shopping-list/items/{item_id}`
- `POST /api/shopping-list/complete`

Alle endpoints gebruiken uitsluitend het actieve server-side sessiehuishouden. Een `household_id` uit de requestbody mag de sessiecontext niet overschrijven.

## Autorisatie

Nieuwe permissies:

- `shopping_list.view`
- `shopping_list.update`
- `shopping_list.manage`

Minimale regels:

- viewer: bekijken;
- member: bekijken en checklist bijwerken;
- admin/owner: volledig beheer en afronden.

De definitieve roltoekenning moet aansluiten op de bestaande autorisatiematrix en wordt met regressietests vastgelegd.

## UI-contract

Schermtitel: `Winkelen`

Tabelkolommen:

1. Gekocht
2. Artikel
3. Aantal
4. Volume
5. Eenheid
6. Opmerking
7. Verwijderen

Standaardgedrag:

- zoekveld `Zoeken` boven Artikel;
- filter Alle/Open/Gekocht;
- sortering alfabetisch op Artikel;
- numerieke waarden rechts uitgelijnd;
- donkergroene checkbox;
- standaard Rezzerv-card, tabel, buttons, modal en exitpositie;
- primaire knop `Winkelen afgerond` alleen actief bij een niet-lege lijst.

## Afrondcontract

Na bevestiging:

1. actieve lijst krijgt status `completed`;
2. `completed_at` en `completed_by` worden gevuld;
3. de zichtbare actieve lijst is leeg;
4. een volgende toevoeging gebruikt een nieuwe actieve lijst;
5. geen enkele voorraad- of bronmutatie vindt plaats.

## Acceptatiecriteria

1. Nieuw huishouden opent een lege Winkelen-tabel.
2. Toegevoegde regels blijven na herladen bestaan.
3. Afvinken blijft na herladen bewaard.
4. Wijzigen en verwijderen werken uitsluitend binnen het actieve huishouden.
5. Afronden maakt de actieve weergave leeg.
6. Afronden wijzigt Voorraad niet.
7. Een gebruiker kan nooit regels van een ander huishouden lezen of muteren.
8. Backend- en frontendbuild zijn groen.
9. Bestaande frontendregressie blijft volledig groen.
10. Nieuwe Winkelen-regressietest is groen.

## Ontwikkelvolgorde

1. database-initialisatie en constraints;
2. shopping-list service;
3. API-router en sessie-autorisatie;
4. backend-selftest;
5. frontendpagina;
6. route en starttegel activeren;
7. frontendregressietest;
8. volledige regressie en scopecontrole;
9. Draft PR voor PO-beoordeling.

## Releasegate

Geen merge, release of deployment zonder:

- groene backendtest;
- groene frontendbuild;
- volledige bestaande frontendregressie groen;
- nieuwe Winkelen-regressie groen;
- gecontroleerde huishoudisolatie;
- QA/QC GO;
- expliciete PO-GO.
