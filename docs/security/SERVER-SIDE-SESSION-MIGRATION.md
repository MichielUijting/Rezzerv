# Rezzerv server-side sessiemigratie

Status: implementatie in uitvoering — NO-GO voor release

Gerelateerd: issue #215

## Bindende architectuur

De browser is geen bron van waarheid voor gebruiker, actief huishouden, rollen of rechten. Browseropslag (`localStorage` en `sessionStorage`) mag geen authenticatie- of autorisatiecontext bevatten.

De browser ontvangt uitsluitend een willekeurige sessie-ID in een beveiligde cookie. De backend herleidt bij ieder beveiligd verzoek opnieuw:

- de geldige sessie;
- de gebruiker;
- het actieve huishouden;
- het huishoudlidmaatschap;
- de actuele rol en rechten;
- de huishoudscope van de opgevraagde data.

## Harde regels

- Geen geldige sessie: HTTP 401.
- Geen bevoegdheid of geen lidmaatschap: HTTP 403.
- Geen fallback naar huishouden `0`.
- Geen impliciete Supergebruiker of standaardbeheerder.
- Frontendvelden zoals `household_id` en `role` zijn nooit autoritatief.
- Een huishoudenwissel is een serveractie en roteert de sessie-ID.
- Een nieuwe login maakt een oudere sessie voor dezelfde browseridentiteit ongeldig.
- De opgeslagen sessietabel bevat geen rol-snapshot; de rol wordt bij ieder verzoek uit `household_memberships` gelezen.

## Cookiecontract

Beoogde cookie:

- naam: `rezzerv_session`;
- `HttpOnly=true`;
- `Secure=true` buiten expliciete lokale ontwikkelmodus;
- `SameSite=Lax` of strenger;
- beperkte levensduur;
- geen gebruiker, huishouden, rol of rechten in de cookiewaarde.

## Implementatievolgorde

1. `server_sessions` en sessieservice.
2. Contracttests voor fail-closed gedrag en rotatie.
3. Login/logout en `GET /api/session` koppelen aan de sessieservice.
4. `POST /api/session/active-household` toevoegen.
5. Bestaande `Authorization`-tokencontext en browseropslag verwijderen.
6. Alle beveiligde routes server-side scopen.
7. Frontend uitsluitend context laten ophalen via `GET /api/session`.
8. Chromium-, Firefox-, WebKit- en regressietests uitvoeren.

## Huidige tranche

Deze branch bevat uitsluitend stap 1 en 2: het server-side sessiefundament en de beveiligingsinvarianttests. De bestaande runtime gebruikt dit fundament nog niet. Daarom blijft de branch en iedere daaruit voortkomende PR nadrukkelijk een NO-GO voor functionele vrijgave totdat de volledige migratie is geïntegreerd en de drie releasegates groen zijn.
