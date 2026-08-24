# 9.1.7f — Platformbeheerder acceptance closure

## Status en doel

9.1.7f sluit de volledige Platformbeheerder-lijn 9.1.7a tot en met 9.1.7e12 application-level af. Deze slice introduceert geen nieuwe productfunctionaliteit, geen nieuwe platformpermission en geen nieuwe autoriteitsbron. De enige correctie aan bestaande testorchestratie is dat de al bestaande Testfixtures-Playwrightregressie voortaan ook expliciet onderdeel is van de canonical volledige frontendregressie.

De acceptance marker voor deze lijn is:

`PLATFORM_ADMIN_9_1_7_ACCEPTANCE_CLOSURE_GREEN`

## Canonical Platformbeheerder-capabilities

| Key | Permission | Route | Functionele bestemming |
| --- | --- | --- | --- |
| diagnostics | `platform.diagnostics.view` | `/platform/diagnostiek` | Diagnostiek |
| logs | `platform.logs.view` | `/platform/logs` | Logs |
| audit | `platform.audit.view` | `/platform/audit` | Audit |
| integrations | `platform.integrations.manage` | `/platform/integraties` | Integraties |
| background-jobs | `platform.background_jobs.manage` | `/platform/achtergrondtaken` | Achtergrondtaken |
| recovery | `platform.recovery.manage` | `/platform/herstel` | Herstel |
| technical-configuration | `platform.technical_configuration.manage` | `/platform/technische-configuratie` | Technische configuratie |
| test-fixtures | `platform.test_fixtures.manage` | `/platform/testfixtures` | Testfixtures |
| feature-flags | `platform.feature_flags.manage` | `/platform/featureflags` | Featureflags |
| sessions | `platform.sessions.revoke` | `/platform/sessies` | Sessies |
| users | `platform.users.suspend` | `/platform/gebruikers` | Gebruikers |
| permissions | `platform.permissions.manage` | `/platform/autorisaties` | Platformautorisaties |

Deze twaalf permissions vormen exact `PLATFORM_ADMIN_PERMISSIONS` en exact de runtimegrants van `platform.platform_admin`.

## Context- en routegrens

Platformbeheerder werkt als een native `context_type="none"`-context. De publieke sessieprojectie bevat geen actief huishouden en de platformroutes worden uit hetzelfde canonical navigatiemodel opgebouwd. Iedere route gebruikt exact de permission van het bijbehorende navigatie-item en opt-in `allowNone`.

Daarmee geldt voor de hele 9.1.7-lijn:

- geen impliciete householdcontext;
- geen household-0/H0-fallback als autoriteit;
- geen `/superuser`-hergebruik voor Platformbeheerder;
- directe platformroute zonder de concrete permission faalt gesloten;
- householdroutes blijven buiten de none-context;
- browsercode fabriceert geen bearer-token of admin-key als alternatieve authority.

Een expliciet household-id kan alleen voorkomen waar een platformoperatie dat id als operationeel doel nodig heeft; het id verleent zelf nooit autorisatie.

## Capability-native authority

De Platformbeheerder-UI is geen zelfstandig autorisatiemodel. De server-side session authority en de canonical authorization foundation blijven beslissend. Permissionchecks worden live server-side geëvalueerd tegen de geregistreerde platformrollen en permissions.

De closure bewaakt daarom gezamenlijk:

- navigatiepermission en routepermission zijn dezelfde canonical key;
- de normale Platformbeheerder heeft exact de twaalf Platformbeheerder-permissions;
- de IP-owner omvat deze twaalf plus zijn expliciete aanvullende authority;
- `platform.special_roles.manage` behoort niet aan de normale Platformbeheerder;
- de bestaande `platform.superuser` blijft tijdens 9.1.7 exact op zijn v1.1 runtimegrantset.

## Logs en Audit blijven gescheiden

9.1.7e2 en 9.1.7e12 sluiten twee verschillende informatiebronnen aan:

- Audit projecteert veilige metadata uit de canonical append-only `auth_audit_log`;
- Logs projecteert een begrensde, gesaniteerde runtimebuffer bovenop bestaande `rezzerv.*` Python logging.

Logs is geen tweede auditmodel en Audit is geen runtime-logviewer. Beide hebben hun eigen canonical permission en veilige browserprojectie.

## Beheerfuncties die met 9.1.7 zijn gesloten

De lijn omvat naast de none-native route- en navigatiefundering onder andere:

- Diagnostiek read-only inzicht;
- Audit read-only inzicht;
- Technische configuratie met expliciet bevestigde canonical acties;
- Testfixtures met expliciete bevestiging en vaste fixtureacties;
- Achtergrondtaken voor uitsluitend self-contained taken;
- Herstel met expliciet operationeel target en destructieve bevestiging;
- Integraties als secret-vrije statusprojectie;
- Featureflags met canonical registry en tweede bevestiging;
- Sessiebeheer met veilige session-id-projectie en targeted revoke;
- Gebruikersbeheer met schorsing en actieve-sessierevocation;
- Platformautorisaties met alleen normale Platformbeheerder als wijzigbare rol binnen deze capability;
- Platformlogs als read-only, gesaniteerde runtimeprojectie.

## Closure-vondst: Testfixtures-regressie

Tijdens de 9.1.7f-inventarisatie bleek `platform-test-fixtures.frontend-regression.spec.js` al te bestaan en focused gevalideerd te zijn, maar niet meer in de hard-coded `test:e2e:frontend-regression` allow-list te staan.

9.1.7f corrigeert uitsluitend die testorchestratiegap door de bestaande spec aan de canonical volledige frontendregressie toe te voegen. De Testfixtures-productcode, endpoints en autorisatie veranderen niet.

## Bewust buiten 9.1.7

De volgende onderwerpen zijn geen onderdeel van deze closure:

- controlled Superuser-v2 runtime cutover;
- mutatie van speciale platformrollen;
- toekennen van `platform.special_roles.manage` aan normale Platformbeheerder of v1.1-Superuser;
- vervanging van het bestaande v1.1-Superuser runtimecontract door `V2_SUPERUSER_TARGET_PERMISSIONS`;
- nieuwe platformtegels of nieuwe Platformbeheerder-permissions;
- nieuwe household/H0-fallbacks;
- hosting-, deployment- of productie-infrastructuurwerk dat niet nodig is voor de application-level closure.

`V2_SUPERUSER_TARGET_PERMISSIONS` blijft dus target-only totdat daarvoor een afzonderlijke, gecontroleerde runtime-cutover wordt ontworpen en geaccepteerd.

## Acceptancecriteria

9.1.7 mag als application-complete worden gemarkeerd wanneer op één exacte PR-head minimaal is bewezen dat:

1. de twaalf canonical key/permission/route-combinaties exact aanwezig zijn;
2. iedere canonical capability naar een concrete functionele pagina dispatcht;
3. `PLATFORM_ADMIN_PERMISSIONS` en `platform.platform_admin` exact dezelfde twaalf permissions bevatten;
4. IP-owner de Platformbeheerder-set omvat maar special-role authority apart houdt;
5. de v1.1-Superuser-grants niet stilzwijgend naar Superuser-v2 zijn uitgebreid;
6. platformroutes uit het canonical navigatiemodel komen en met exact hun concrete permission `allowNone` gebruiken;
7. `/superuser` en huishoudroutes hun eigen grenzen behouden;
8. de concrete Platformbeheerder-pagina's geen bearer/admin-key authority fabriceren;
9. de canonical volledige frontendregressie alle Platformbeheerder-specs bevat, inclusief Testfixtures;
10. het authorization-foundation contract, representatieve platformroute-contracten, server-session security, production frontend build, volledige Playwright-regressie en release package groen zijn;
11. de closure-selftest eindigt met `PLATFORM_ADMIN_9_1_7_ACCEPTANCE_CLOSURE_GREEN`.

Na deze acceptance is de logische vervolgfase een afzonderlijke inventarisatie en gecontroleerde cutover voor Superuser-v2/special-role authority, niet een 9.1.7e13-capability.
