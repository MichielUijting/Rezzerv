# PR #214 — PO-acceptatietest

## Doel

Deze test beoordeelt functioneel het nieuwe Meldingenmechanisme en het autorisatiemodel met huishoudrollen en centrale platformrollen.

## Voorwaarden

- De featurebranch `feature/support-message-frontend` is lokaal gestart.
- Backend: `http://localhost:8011`.
- Frontend: `http://localhost:5174`.
- De vaste Supergebruiker is ingericht in huishouden 0.
- Gebruik geen oud account `admin@rezzerv.local` en geen algemeen token `rezzerv-dev-token`.

## Testaccount Supergebruiker

- E-mail: `supergebruiker@rezzerv.local`
- Wachtwoord: het lokaal ingestelde Supergebruikerswachtwoord. In een ongewijzigde ontwikkelomgeving is de ontwikkelstandaard `RezzervSuper123!`.

## Test 1 — Inloggen als Supergebruiker

1. Open `http://localhost:5174/login`.
2. Log in als vaste Supergebruiker.
3. Controleer dat het startscherm opent.
4. Controleer dat geen melding over een verlopen of onbevoegde sessie verschijnt.

**Verwacht:** inloggen lukt en de sessie is gekoppeld aan `supergebruiker@rezzerv.local` en huishouden 0.

## Test 2 — Centrale Meldingen

1. Open `/admin/meldingen`.
2. Controleer dat het totaaloverzicht opent.
3. Filter op status.
4. Open een melding.
5. Voeg een antwoord toe.
6. Wijzig de status en ververs het scherm.

**Verwacht:** overzicht, filter, conversatie, antwoord en statuswijziging werken; de wijziging blijft na verversen zichtbaar.

## Test 3 — Huishoudmelding

1. Log in als een gewone gebruiker van een testhuishouden.
2. Open `/meldingen`.
3. Maak een nieuwe melding.
4. Open de conversatie en voeg een aanvullend bericht toe.

**Verwacht:** de gebruiker ziet alleen meldingen van het eigen huishouden.

## Test 4 — Huishoudisolatie

1. Gebruik twee gebruikers uit verschillende testhuishoudens.
2. Maak in huishouden A een melding.
3. Log in als gebruiker van huishouden B.
4. Controleer het meldingenoverzicht en probeer de melding van A niet via handmatige URL-manipulatie te openen.

**Verwacht:** huishouden B ziet en opent de melding van huishouden A niet.

## Test 5 — Huishoudrollen

Controleer met een Eigenaar, Lid en Kijker:

- **Eigenaar:** kan leden en huishoudinstellingen beheren.
- **Lid:** kan reguliere huishoudhandelingen uitvoeren, maar geen eigenaarsbeheer.
- **Kijker:** heeft uitsluitend leesrechten op ondersteunde huishoudfuncties.

**Verwacht:** rechten volgen de rol; een huishoudrol verleent nooit centrale platformtoegang.

## Test 6 — Centrale routebeveiliging

1. Log in als gewone huishoud-Eigenaar zonder centrale rol.
2. Open achtereenvolgens:
   - `/admin/meldingen`
   - `/admin/gebruikers`
   - `/catalogus`
   - `/externe-databases`
3. Herhaal als vaste Supergebruiker.

**Verwacht:** de gewone Eigenaar wordt naar een toegestane omgeving teruggeleid; de Supergebruiker krijgt toegang volgens de centrale bevoegdheden.

## Test 7 — Frontteam

1. Log in als een gebruiker met alleen de centrale rol Frontteam.
2. Controleer Catalogus en Externe databases.
3. Controleer dat Supergebruikerfuncties, zoals centraal gebruikersbeheer, niet beschikbaar zijn wanneer de benodigde bevoegdheid ontbreekt.

**Verwacht:** Frontteam heeft uitsluitend de expliciet toegekende centrale bevoegdheden.

## Test 8 — Oude toegang blokkeren

Controleer dat niet kan worden ingelogd of geauthenticeerd met:

- `admin@rezzerv.local` als oud centraal beheeraccount;
- het algemene token `rezzerv-dev-token` zonder expliciete gebruikersidentiteit.

**Verwacht:** beide oude toegangspaden worden geweigerd.

## Technisch testscherm `/admin`

`/admin` is een intern testdata- en regressiescherm. Het bevat onder meer reset-, seed-, purge- en regressieacties. Het is geen regulier huishoudbeheerscherm en valt buiten de functionele PO-acceptatie van Meldingen en autorisatie. Voor een productierelease moet dit scherm apart als ontwikkel-/testfunctie worden behandeld.

## Acceptatie

De PO geeft alleen GO wanneer alle bovenstaande functionele tests slagen en er geen regressie zichtbaar is in bestaande voorraad-, kassabon-, uitpak- en artikelprocessen.

Een PO-GO is geen automatische merge-opdracht. Merge naar `main` gebeurt uitsluitend na een afzonderlijke, expliciete opdracht.
