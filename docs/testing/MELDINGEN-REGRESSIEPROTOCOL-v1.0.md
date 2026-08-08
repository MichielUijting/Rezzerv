# Rezzerv Meldingen – Regressieprotocol v1.0

## Doel

Dit protocol voorkomt dat de Meldingen-functionaliteit opnieuw uit navigatie, routes, autorisatie, API, opslag of gebruikersinterface verdwijnt.

## Verplichte automatische controles

De volgende bestaande audits en workflows vormen samen de vaste regressieset:

1. `frontend/tests/support_message_role_routing_audit.py`
   - gebruiker opent `/meldingen`;
   - superuser opent `/superuser/meldingen`;
   - platformroute is permissiebeveiligd.

2. `frontend/tests/support_message_improvements_audit.py`
   - standaardfilter Open;
   - zichtbare verversingsstatus;
   - verwijderen aan beide kanten;
   - centrale Rezzerv-bevestiging;
   - geen `window.confirm`;
   - lichtgroene markering;
   - titel vet en berichttekst normaal.

3. `frontend/tests/support_message_broadcast_audit.py`
   - broadcastformulier bestaat;
   - alleen platformmutatie is toegestaan;
   - broadcast-API en route zijn geregistreerd;
   - actieve leden worden geselecteerd;
   - `user_email` en `app_users` worden ondersteund;
   - systeemhuishouden 0 en de superuser worden uitgesloten;
   - ieder lid krijgt een eigen gesprek;
   - de superuser blijft afzender.

4. Bestaande support-API- en sessietests
   - huishoudisolatie;
   - platformpermissies;
   - cookiegebaseerde sessieautoriteit;
   - persistente opslag en conversaties.

## Verplichte handmatige PO-steekproef

Gebruik twee gescheiden browsersessies.

### A. Gebruiker naar superuser

- Log in als gewone gebruiker.
- Maak een melding met herkenbaar onderwerp.
- Controleer dat de melding in Mijn meldingen staat.
- Log in een andere browser als superuser.
- Controleer dat exact dezelfde thread zichtbaar is.
- Antwoord als superuser.
- Controleer automatische ontvangst en lichtgroene markering bij de gebruiker.
- Antwoord als gebruiker en controleer ontvangst bij de superuser.
- Wijzig de status en controleer consistentie.

### B. Verwijderen

- Klik op de groene vuilnisbak.
- Controleer de centrale Rezzerv-bevestiging.
- Annuleer eenmaal.
- Bevestig daarna verwijderen.
- Controleer dat de thread aan beide kanten volgens bevoegdheid verdwijnt.

### C. Broadcast

- Log in als `supergebruiker@rezzerv.local`.
- Controleer het formulier Nieuwe melding aan alle leden.
- Verstuur een broadcast met antwoorden toegestaan.
- Controleer de gerapporteerde ontvangers.
- Controleer bij ten minste twee actieve gebruikers dat ieder een eigen gesprek ontvangt.
- Controleer dat gebruikers elkaars gesprek niet kunnen zien.
- Controleer dat antwoorden afzonderlijk bij de superuser binnenkomen.

### D. Negatieve autorisatie

- Controleer dat Beheerder, Lid en Frontteam geen broadcastformulier zien.
- Controleer dat directe toegang tot de platformroute zonder superuserpermissie wordt geweigerd.
- Controleer dat een gebruiker geen thread van een andere gebruiker kan openen of verwijderen.

## NO-GO-criteria

De release is NO-GO wanneer één van deze punten optreedt:

- Meldingen-tegel ontbreekt;
- verkeerde route per rol;
- een thread verdwijnt bij opnieuw inloggen of containerrebuild;
- gebruiker ziet een gesprek van een ander;
- superuser ziet een nieuwe melding niet;
- antwoorden of status lopen uiteen;
- automatische verversing werkt slechts aan één kant;
- standaardfilter is niet Open;
- browser-`confirm` wordt gebruikt;
- broadcast is zichtbaar voor een niet-superuser;
- actieve leden worden niet gevonden;
- dubbele broadcasts worden aangemaakt;
- systeemhuishouden 0 ontvangt een gewone broadcast;
- CI-audit of documentatiecontract faalt.

## Bewijsvoering

Voor een GO worden bewaard:

- commit-SHA;
- workflowresultaten;
- PO-testdatum;
- gebruikte rollen/accounts;
- eventuele screenshots;
- aantal broadcastontvangers;
- bevestiging dat PR niet automatisch is gemerged of vrijgegeven.

## Positieve PO-test

Op 2026-08-01 heeft de Product Owner de volledige gebruikersketen, de verbeterpunten en de superuserbroadcast positief getest.

## Hertesttriggers

Dit protocol moet opnieuw worden uitgevoerd na wijzigingen aan:

- `HouseholdSupportPage.jsx`;
- `PlatformSupportPage.jsx`;
- `supportApi.js`;
- support- of broadcastbackendroutes;
- `support_message_service.py`;
- `AppFeedbackProvider.jsx`;
- routering of HomePage-tegels;
- sessie- en autorisatiemechanisme;
- `app_users` of `household_memberships`;
- database- of Dockerpersistentieregels.