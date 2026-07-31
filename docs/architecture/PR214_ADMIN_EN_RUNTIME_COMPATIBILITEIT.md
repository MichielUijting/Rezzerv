# PR #214 — beoordeling `/admin` en runtimecompatibiliteit

## Samenvatting

Deze beoordeling sluit de twee resterende technische aandachtspunten van PR #214 af zonder risicovolle fysieke opschoning in het monolithische `backend/app/main.py` af te dwingen.

## Oude admin- en tokencompatibiliteit

### Beoordeling

De actieve runtime gebruikt de nieuwe authenticatie- en autorisatielaag:

- het algemene token `rezzerv-dev-token` wordt geweigerd;
- alleen een expliciet aan een identiteit gekoppeld ontwikkeltoken wordt geaccepteerd;
- `admin@rezzerv.local` wordt niet meer als vaste centrale beheeridentiteit gebruikt;
- de vaste centrale identiteit is `supergebruiker@rezzerv.local`;
- centrale toegang volgt uit persistente platformrollen;
- huishoudrollen Eigenaar, Lid en Kijker blijven als afzonderlijke rollen behouden.

### Besluit

De oude codefragmenten in `main.py` zijn runtime-compatibiliteitsrestanten en geen actief autorisatiemodel meer. Fysieke verwijdering wordt uit deze functionele PR gehouden omdat:

1. `main.py` veel niet-gerelateerde routes en regressieketens bevat;
2. de runtimevervanging en gerichte tests het oude toegangspad al blokkeren;
3. fysieke opschoning een afzonderlijke, controleerbare refactor met eigen routecatalogus- en regressiebewijs hoort te zijn.

Dit is geen functionele openstaande blokkade voor PR #214. Er hoort wel een aparte technische refactoropdracht voor definitieve verwijdering te volgen.

## Beoordeling algemeen `/admin`-scherm

### Aangetroffen functies

Het scherm bevat technische beheer- en testfuncties, waaronder:

- demo- en artikeltestdata genereren;
- testdata resetten;
- ruimtes, sublocaties en voorraadregels handmatig aanmaken;
- gearchiveerde kassabonnen definitief verwijderen;
- kassa-inleesregressies en smoke-tests uitvoeren;
- technische aantallen en regressierapporten tonen.

### Classificatie

`/admin` is daarmee geen regulier huishoudbeheerscherm en ook geen centrale productfunctie voor Frontteam. Het is een intern ontwikkel-, test- en onderhoudsscherm met potentieel destructieve acties.

### Besluit per categorie

| Functiecategorie | Beoordeling | Besluit |
|---|---|---|
| Demo-/testdata genereren | Alleen voor ontwikkeling en test | Niet opnemen als normale huishoudfunctie |
| Reset testdata | Destructief | Alleen gecontroleerde ontwikkel-/testomgeving |
| Handmatig technische data invoeren | Testondersteuning | Geen reguliere platformfunctie |
| Purge gearchiveerde bonnen | Productiedata-destructief | Apart productierecht en audit vereist vóór productiegebruik |
| Kassa regressie/smoke | QA-functie | Alleen ontwikkel-/testomgeving |
| Technische status | Diagnostiek | Alleen bevoegde technische gebruikers |

### Relatie met nieuwe centrale schermen

De echte centrale productfuncties zijn reeds afzonderlijk onder expliciete platformbevoegdheden geplaatst:

- `/admin/meldingen`;
- `/admin/gebruikers`;
- `/catalogus`;
- `/externe-databases`.

Deze routes mogen niet worden verward met het technische `/admin`-testscherm.

## Releasebesluit

Voor PR #214 geldt:

- `/admin` valt buiten de functionele PO-acceptatie van Meldingen en het nieuwe autorisatiemodel;
- het scherm blijft een technisch testscherm;
- een productierelease moet het scherm afzonderlijk uitschakelen, verbergen of voorzien van een expliciete technische Supergebruikerbevoegdheid en backendhandhaving;
- deze vervolgmaatregel hoort in een afzonderlijke, kleine hardening-PR en niet als verborgen uitbreiding van PR #214.

## Bewijsstatus

Op commit `426fa23099d171d074b190ec33122ca21dc515ae` waren alle 26 CI-controles groen. Latere documentatiecommits wijzigen geen runtimecode, maar de actuele branch-controles moeten vóór PO-GO opnieuw worden gecontroleerd.
