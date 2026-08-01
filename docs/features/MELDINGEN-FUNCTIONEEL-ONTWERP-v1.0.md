# Rezzerv Meldingen – Functioneel ontwerp v1.0

## Status

- Functionele status: **PO-GO**
- Bevestigd op: 2026-08-01
- Branch: `agent/server-side-session-foundation`
- PR: #216
- Merge-/releasestatus: nog niet gemerged of vrijgegeven

## Doel

Meldingen ondersteunt communicatie tussen Rezzerv-gebruikers en de centrale superuser. Iedere conversatie blijft afgeschermd per gebruiker en huishouden.

## Rollen en bevoegdheden

### Gewone gebruiker

- ziet de tegel **Meldingen**;
- opent `/meldingen`;
- maakt een melding aan de superuser;
- ziet uitsluitend eigen meldingen;
- leest en beantwoordt het eigen gesprek;
- kan een eigen melding verwijderen;
- kan geen platformbreed bericht versturen.

### Superuser

- opent via de tegel automatisch `/superuser/meldingen`;
- ziet meldingen van alle huishoudens;
- leest en beantwoordt ieder gesprek;
- wijzigt de status naar Open, In behandeling of Gesloten;
- filtert op status en huishouden;
- exporteert meldingen als CSV;
- verwijdert meldingen;
- stuurt als enige een melding aan alle actieve Rezzerv-leden.

### Beheerder, Lid en Frontteam

Deze rollen hebben geen platformbreed broadcastrecht. Een huishoudrol op zichzelf geeft geen toegang tot `/superuser/meldingen`.

## Functioneel gedrag

### Gebruikersmelding naar superuser

1. De gebruiker vult onderwerp en bericht in.
2. De melding wordt centraal opgeslagen.
3. De gebruiker ziet de melding in **Mijn meldingen**.
4. De superuser ziet dezelfde conversatie in **Alle meldingen**.
5. Beide partijen kunnen binnen dezelfde thread antwoorden.
6. Status en berichtinhoud blijven consistent aan beide kanten.

### Automatische verversing

- Beide schermen verversen automatisch.
- Het scherm toont het tijdstip en de cyclus van de laatste verversing.
- Nieuwe antwoorden worden zonder handmatige paginaverversing zichtbaar.

### Ongelezen antwoord

- Wanneer het laatste bericht van de andere partij komt, wordt het lijstpaneel lichtgroen gearceerd.
- Na openen geldt het gesprek in de actuele sessie als gelezen en verdwijnt de markering.

### Filters

- De standaardfilter is **Open**.
- Andere keuzes zijn Alle statussen, In behandeling en Gesloten.

### Verwijderen

- Iedere melding heeft een groen vuilnisbakicoon.
- Verwijderen gebruikt het centrale `AppFeedbackProvider`-component.
- De bevestiging bevat Verwijderen en Annuleren.
- Een gewone gebruiker kan uitsluitend een eigen melding verwijderen.
- De superuser kan meldingen vanuit het platformoverzicht verwijderen.

### Platformbericht aan alle leden

- Alleen de superuser ziet **Nieuwe melding aan alle leden**.
- Het formulier bevat onderwerp, bericht en Antwoorden toestaan.
- Verzending gebruikt het centrale bevestigingscomponent.
- De ontvangers worden bepaald uit actieve lidmaatschappen.
- `household_memberships.user_email` wordt gekoppeld aan het interne gebruikers-ID in `app_users`.
- Systeemhuishouden `0` en de superuser zelf worden uitgesloten.
- Dubbele ontvangers worden voorkomen.
- Ieder actief lid krijgt een eigen, afgeschermde conversatie.
- De superuser blijft als afzender zichtbaar.

## Presentatieregels

- Titel van de geselecteerde melding is vet.
- Berichtinhoud is normaal gezet.
- De centrale Rezzerv-meldingsconventie wordt gebruikt voor bevestigingen en fouten.
- Een standaard browserdialoog zoals `window.confirm` is niet toegestaan.

## Persistente opslag

De meldingenketen gebruikt:

- `support_threads`;
- `support_messages`;
- `support_recipients`.

Container-rebuilds mogen bestaande meldingen niet verwijderen.

## Autorisatiecontract

- Huishoudroutes gebruiken de actuele server-side sessie en actieve huishoudcontext.
- Platformroutes vereisen `platform.support_access.read` of `platform.support_access.mutate`.
- Alleen de canonieke superuser heeft het broadcastrecht.
- Gebruikers mogen geen gesprekken van andere gebruikers openen, beantwoorden of verwijderen.

## Positieve PO-acceptatie

De Product Owner heeft positief getest:

- melding van Huishouden2 naar de superuser;
- zichtbaarheid van dezelfde thread aan beide kanten;
- antwoorden over en weer;
- statusconsistentie;
- automatische verversing;
- standaardfilter Open;
- lichtgroene ongelezenmarkering;
- verwijderen via centraal Rezzerv-component;
- platformbericht door de superuser aan alle actieve leden;
- ontvangst als afzonderlijke, afgeschermde gesprekken.

## Wijzigingsregel

Een wijziging aan routes, permissies, sessies, lidmaatschappen, meldingenopslag, frontendnavigatie of centrale feedbackcomponenten vereist heruitvoering van het Meldingen-regressieprotocol.