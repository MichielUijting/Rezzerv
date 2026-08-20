# Rezzerv server-side sessiemigratie

Status: implementatie in uitvoering — NO-GO voor release

Gerelateerd: issue #215 en draft PR #216

Dit document beschrijft de bestaande sessie- en autorisatieruntime rond v1.1.
Het PO-goedgekeurde functionele doelcontract voor het nieuwe rollen- en
accountmodel staat in `docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md`. De
afzonderlijke implementatiestap 9.1 moet beide bewust in overeenstemming
brengen; deze documentatietaak verandert de runtime niet.

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
4. Bestaande centrale Authorization-context vervangen door de server-side requestcontext. **Gerealiseerd in tranche 3.**
5. `POST /api/session/active-household` toevoegen. **Nog open.**
6. Resterende browseropslag en Authorization-headers uit frontend en routecontracten verwijderen. **Nog open.**
7. Alle domeinqueries en uitzonderingsroutes aantoonbaar server-side scopen. **Audit in uitvoering.**
8. Frontend uitsluitend context laten ophalen via `GET /api/session`. **Nog open.**
9. Chromium-, Firefox-, WebKit-, Docker- en regressietests uitvoeren. **In uitvoering.**

## Runtime-activering tranche 2

De Docker-runtime start via `app.session_entrypoint:app`. Dit entrypoint:

- importeert de bestaande FastAPI-app zonder overige domeinlogica te dupliceren;
- verwijdert uitsluitend de legacy-routes voor login, logout en sessie-opvraag;
- registreert de nieuwe sessierouter exact eenmaal;
- stopt de applicatiestart wanneer een vereiste sessieroute ontbreekt of dubbel geregistreerd is;
- behoudt alle overige bestaande routes.

## Server-side routecontext tranche 3

Het runtime-entrypoint installeert nu tevens een requestgebonden context voor de opaque sessiecookie. De centrale legacy-guards worden bij applicatiestart vervangen door adapters die uitsluitend deze server-side context gebruiken:

- `get_current_user_from_authorization` wordt vervangen door een adapter die de Authorization-waarde volledig negeert;
- `require_household_context` wordt vervangen door een adapter die gebruiker, rol en actief huishouden opnieuw uit de serversessie resolveert;
- een Bearer-token zonder geldige sessiecookie levert altijd HTTP 401;
- een aangevraagde `household_id` die niet gelijk is aan het actieve serverhuishouden levert HTTP 403;
- een frontendverzoek kan daardoor niet zelfstandig van huishouden wisselen;
- bestaande routes die via deze centrale functies lopen, krijgen de nieuwe context zonder wijziging van hun domeinimplementatie.

De middleware bewaart alleen de opaque cookiewaarde in een requestlokale `ContextVar`. Iedere daadwerkelijke autorisatie-opvraag leest het sessierecord en het actuele lidmaatschap opnieuw uit de database.

Voor tranche 3 is een afzonderlijke GitHub Actions-gate toegevoegd: `Server-side session security`. Deze voert de sessieservice-, endpoint-, entrypoint- en requestcontexttests gezamenlijk uit.

## Autorisatiematrix en regressiegate

De server-side sessiecontext is gekoppeld aan de door de Product Owner vastgestelde autorisatiematrix v1.1.

Canonieke documentatie:

```text
docs/security/AUTORISATIEMECHANISME-EN-MATRIX-v1.1.md
```

Uitvoerbare matrixacceptatietest:

```text
backend/app/testing/authorization_matrix_acceptance.py
```

Lokaal startprogramma:

```text
RUN_AUTORISATIEMATRIX_TEST.bat
```

CI-regressiegate:

```text
.github/workflows/authorization-matrix-acceptance.yml
```

De gate voert 190 controles uit en geeft alleen GO wanneer alle rol-permissiecombinaties en aanvullende structuurregels overeenkomen met matrix v1.1. Dezelfde workflow controleert dat de canonieke autorisatiedocumentatie en het regressieprotocol aanwezig en onderling consistent zijn.

Het handmatige vervolgprotocol staat in:

```text
docs/testing/AUTORISATIE-REGRESSIEPROTOCOL-v1.1.md
```

Een wijziging aan sessies, rollen, permissies, routeguards, Admin, Catalogus, GPC, Externe databases of platformbeheer verplicht tot een nieuwe volledige matrixacceptatietest en UI-steekproef.

## Huidige releasebeoordeling

Tranche 3 is code-technisch aangesloten, maar de volledige migratie is nog niet afgerond. De frontend verstuurt mogelijk nog Authorization-context en gebruikt mogelijk nog browseropslag. Daarnaast moet de resterende route- en queryscope systematisch worden geaudit en moet de server-side huishoudenwissel nog worden toegevoegd. Daarom blijft PR #216 **Draft en NO-GO** totdat de volledige migratie is geïntegreerd en Scope Gate, QA/QC Gate en Packaging Gate groen zijn.
