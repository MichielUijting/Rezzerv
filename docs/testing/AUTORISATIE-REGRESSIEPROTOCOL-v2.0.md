# Rezzerv autorisatie-regressieprotocol v2.0

Status: **9.1.9 acceptance candidate**. Dit protocol wordt canonical na succesvolle merge van de 9.1.9 acceptance closure.

## 1. Doel

Dit protocol valideert het rollen- en accountmodel v2 als geheel. Het historische v1.1-protocol blijft alleen beschikbaar voor legacy/household compatibility en is geen volledige beschrijving van de platformrollenruntime meer.

## 2. Te bewijzen rollen en contexten

| Actor | Context | Verplichte kernbewijzen |
|---|---|---|
| Lid | `regular` | household memberrechten, geen platformauthority |
| Beheerder | `regular` | memberrechten + household beheer, geen platformauthority |
| Frontteamlid | `regular` | eigen household admin + exacte Frontteam-platformrechten, geen toegang tot andere huishoudens |
| Superuser | `system` | H0 + exacte functionele Superuser-v2 platformset, geen technische Platformbeheerderrechten |
| Platformbeheerder | `none` | exacte technische Platformbeheerder-set, geen household-/Superuserfallback |
| Superuser + Platformbeheerder | `system` | union van beide permission-sets, geen IP-owner-only special-role authority |
| IP-owner | `system` | exacte protected union incl. `platform.special_roles.manage`, zonder extra role rows te vereisen |

## 3. Algemene security-invarianten

Iedere relevante regressie moet waar van toepassing bewijzen:

- server-side sessie is identity- en contextauthority;
- browser supplied household-id verleent geen authority;
- forged Bearer/admin-key verleent geen canonical sessionauthority;
- `regular`, `system` en `none` blijven expliciet gescheiden;
- H0 is geen regulier huishouden en geen fallback;
- e-mailadres alleen verleent geen H0/Superuserauthority;
- platformpermissions worden live server-side geëvalueerd;
- rolrevocatie werkt op de eerstvolgende relevante request/sessionresolution;
- raw platformrollen worden niet als browserauthority gepubliceerd;
- Frontteam is een aparte platformrol bovenop het eigen reguliere `household.admin`-lidmaatschap;
- normale household rolmutatie kan alleen Lid en Beheerder toekennen;
- legacy viewer/advanced-member data blijft non-destructief compatible maar is geen nieuw toewijsbare productrol;
- `platform.special_roles.manage` is uitsluitend IP-owner.

## 4. Permission-partition

### Superuser-v2

Exact `V2_SUPERUSER_TARGET_PERMISSIONS`. Geen overlap met `PLATFORM_ADMIN_PERMISSIONS` en geen `platform.special_roles.manage`.

### Platformbeheerder

Exact `PLATFORM_ADMIN_PERMISSIONS`. Geen functionele Superuserrechten of automatische H0-toegang.

### Superuser + Platformbeheerder

Exact de union van beide sets. De combinatie krijgt daardoor niet `platform.special_roles.manage`.

### IP-owner

Exact:

`V2_SUPERUSER_TARGET_PERMISSIONS | PLATFORM_ADMIN_PERMISSIONS | {"platform.special_roles.manage"}`

Een IP-owner-only system-session moet deze platformset publiek als permissions projecteren zonder `platform_roles` te exposen.

## 5. Bestaande functionele domeinen

De umbrella closure moet minstens de volgende bestaande boundaries meenemen:

- Meldingen/support: `platform.support_access.*`;
- Externe productbronnen: `platform.external_products.*`;
- centrale catalogus: `platform.catalog.*`;
- GPC functioneel: `platform.gpc.*`;
- technische GPC-import: `platform.technical_configuration.manage`;
- externe databronconfiguratie: `platform.external_sources.*`;
- systeemhuishouden 0;
- special-role management;
- server-side session/context foundation.

## 6. Executable testlagen

### A. Roles-v2 umbrella closure

Workflow: `Roles v2 9.1 acceptance closure validation`.

Deze gate draait minimaal:

- `test_roles_v2_acceptance_closure.py`;
- `test_authorization_role_matrix.py`;
- roles-v2 foundation;
- server session service;
- special-role management;
- Superuser+Platformbeheerder stacking;
- Frontteam personal household;
- support platform authorization;
- external database authorization;
- GPC-NL platform authorization;
- de bestaande household compatibility authorization matrix;
- server-session security selftest.

### B. Focused bestaande gates

Bestaande dedicated workflows blijven beslissend voor hun eigen boundaries, waaronder Superuser-v2, Platformbeheerder, Frontteam, Platformautorisaties en sessiebeveiliging.

### C. Productbrede regressie

Voor Ready moeten daarnaast de volledige frontendregressie en de canonical release package-gate groen zijn op dezelfde kandidaat-head.

## 7. Betekenis van de historische matrix

`backend/app/testing/authorization_matrix_acceptance.py` blijft bewust bestaan omdat de householdrechtenmatrix nog waardevolle backward-compatibilitydekking levert. De test is echter niet langer de volledige rollen-v2 acceptatiematrix: Platformbeheerder, stacking en IP-owner worden canonical afgedekt door het v2 umbrella-contract.

De v1.1-documenten blijven als historische referentie aanwezig om regressies en oude datamodellen te kunnen duiden, maar mogen na 9.1-closure niet als zelfstandige platformauthoritybron worden gebruikt.

## 8. Ready/merge-regel

Geen Ready of merge wanneer:

- één relevante exact-head workflow rood of lopend is;
- de PR-head is veranderd na de laatste acceptatie;
- `main` onverwacht is verplaatst;
- compare/merge-base niet schoon is;
- onverwachte filescope bestaat;
- unresolved reviewthreads of blockers aanwezig zijn.

Merge gebruikt de normale Rezzerv `expected_head_sha`-guard en wordt gevolgd door verificatie van nieuwe `main`, mergeparents, signature en branchbehoud.
