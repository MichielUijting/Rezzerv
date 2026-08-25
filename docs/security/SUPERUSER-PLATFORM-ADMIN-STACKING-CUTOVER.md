# 9.1.8c — Superuser + Platformbeheerder session/account-context stacking cutover

Status: implementatieslice voor het v2 gecombineerde platformaccountmodel.

## Doel

Een account mag tegelijk de gewone speciale rollen `platform.superuser` en `platform.platform_admin` dragen.

De combinatie krijgt geen vierde accountcontext en geen parallel autorisatiemodel. Omdat Superuser toegang tot het systeemhuishouden H0 verleent, gebruikt een gestapeld account exact één `system`-sessie op H0. De technische Platformbeheerderrechten worden in dezelfde sessie geprojecteerd als aanvullende platformpermissions.

## Canonical runtime

- `platform.superuser` alleen: H0 / `context_type=system`.
- `platform.platform_admin` alleen: geen huishouden / `context_type=none`.
- `platform.superuser` + `platform.platform_admin`: H0 / `context_type=system`.
- de publieke sessiepayload projecteert voor de stack de union van de actieve Superuser- en Platformbeheerderpermissions;
- `platform_roles` wordt niet naar de browser geprojecteerd;
- backend platformroute-authority blijft live server-side via de bestaande permission evaluator.

De stack verleent nooit `platform.special_roles.manage`; die permission blijft exclusief van de beschermde IP-eigenaar.

## Fail-closed combinaties

9.1.8c opent uitsluitend Superuser + Platformbeheerder. De bestaande blokkades blijven staan voor:

- Frontteam + Superuser;
- Frontteam + Platformbeheerder;
- Frontteam + IP-eigenaar;
- IP-eigenaar + Platformbeheerder.

Een gestapeld account mag geen regulier huishoudlidmaatschap hebben. Een Platformbeheerder-only account kan geen H0-sessie maken en een gestapeld account kan geen `none`-sessie maken zolang Superuser actief is.

## Lifecycle

### Platformbeheerder intrekken

Wanneer `platform.platform_admin` wordt ingetrokken terwijl Superuser actief blijft:

- de bestaande H0-sessie blijft geldig;
- `context_type=system` blijft behouden;
- Superuserpermissions blijven actief;
- technische Platformbeheerderpermissions verdwijnen bij de volgende server-side sessieresolutie.

### Superuser intrekken

Wanneer `platform.superuser` wordt ingetrokken terwijl Platformbeheerder actief blijft:

- de bestaande H0-sessie wordt direct fail-closed;
- een volgende login resolveert het account als Platformbeheerder-only;
- de nieuwe sessie krijgt `context_type=none` en geen actief huishouden.

Daarmee kan een H0-cookie nooit stil blijven functioneren nadat de rol die H0 verleent is ingetrokken.

## Acceptatie 9.1.8c

Voor Ready moet één exacte PR-head aantoonbaar bewijzen:

1. special-role grant werkt in beide stackingrichtingen;
2. login van de stack kiest H0/system-context;
3. system-session creation en resolution accepteren exact Superuser + Platformbeheerder;
4. publieke sessiepermissions bevatten de Superuser-v2 + Platformbeheerder-union;
5. geen browserprojectie van `platform_roles`;
6. `platform.special_roles.manage` blijft afwezig;
7. Platformbeheerder-revoke houdt H0 als Superuser geldig en verwijdert technische permissions;
8. Superuser-revoke maakt de bestaande H0-sessie ongeldig en laat een volgende Platformbeheerder-login naar `none` gaan;
9. IP-eigenaar + Platformbeheerder en alle Frontteamconflicten blijven fail-closed;
10. bestaande Superuser-only, Platformbeheerder-only en sessieregressies blijven groen;
11. volledige frontend/Playwright-regressie is groen;
12. canonical release package is groen.
