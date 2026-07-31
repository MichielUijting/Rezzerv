# Rezzerv server-side sessiemigratie

Status: implementatie in uitvoering — NO-GO voor release

Gerelateerd: issue #215 en draft PR #216

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
- Een nieuwe login maakt een oudere actieve sessie van dezelfde gebruiker ongeldig.
- De opgeslagen sessietabel bevat geen rol-snapshot; de rol wordt bij ieder verzoek uit `household_memberships` gelezen.

## Cookiecontract

Beoogde cookie:

- naam: `rezzerv_session`;
- `HttpOnly=true`;
- `Secure=true` buiten expliciete lokale ontwikkel- of testmodus;
- `SameSite=Lax` of strenger;
- beperkte levensduur;
- geen gebruiker, huishouden, rol of rechten in de cookiewaarde.

## Implementatievolgorde

1. `server_sessions` en sessieservice. **Gerealiseerd in branch.**
2. Contracttests voor fail-closed gedrag en rotatie. **Gerealiseerd in branch.**
3. Login/logout en `GET /api/session` koppelen aan de sessieservice. **Gerealiseerd en als runtime-entrypoint geactiveerd in branch.**
4. `POST /api/session/active-household` toevoegen. **Nog open.**
5. Bestaande `Authorization`-tokencontext en browseropslag verwijderen. **Nog open.**
6. Alle beveiligde routes server-side scopen. **Nog open.**
7. Frontend uitsluitend context laten ophalen via `GET /api/session`. **Nog open.**
8. Chromium-, Firefox-, WebKit-, Docker- en regressietests uitvoeren. **In uitvoering; GitHub-controles lopen.**

## Runtime-activering tranche 2

De Docker-runtime start via `app.session_entrypoint:app`. Dit entrypoint:

- importeert de bestaande FastAPI-app zonder overige domeinlogica te dupliceren;
- verwijdert uitsluitend de legacy-routes voor login, logout en sessie-opvraag;
- registreert de nieuwe sessierouter exact eenmaal;
- stopt de applicatiestart wanneer een vereiste sessieroute ontbreekt of dubbel geregistreerd is;
- behoudt alle overige bestaande routes.

Hiermee wordt vermeden dat twee handlers met hetzelfde pad actief blijven, terwijl de fysieke opschoning van de grote legacy-authsectie als afzonderlijke, gecontroleerde refactor kan plaatsvinden.

## Huidige releasebeoordeling

Tranche 2 is code-technisch aangesloten, maar de volledige migratie is nog niet afgerond. De bestaande beveiligde domeinroutes vertrouwen nog grotendeels op de oude Authorization-context en de frontend is nog niet omgezet. Daarom blijft PR #216 **Draft en NO-GO** totdat de volledige migratie is geïntegreerd en Scope Gate, QA/QC Gate en Packaging Gate groen zijn.
