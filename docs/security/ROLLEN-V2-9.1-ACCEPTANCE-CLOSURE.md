# Rollen- en accountmodel v2 — 9.1 acceptance closure

Status: **9.1.9 acceptance candidate**. Dit document sluit geen PR zelfstandig; de exacte kandidaat-head moet alle genoemde executable gates groen doorlopen voordat 9.1 als afgerond mag worden beschouwd.

## 1. Doel

9.1.9 voegt geen nieuwe productfunctionaliteit toe. De tranche sluit de overgang van het historische v1.1-autorisatiecontract naar het PO-goedgekeurde `ROLLEN-EN-ACCOUNTMODEL-v2.0.md` door:

- het geïmplementeerde rollen-/account-/contextmodel als één geheel executable te bewijzen;
- resterende transitional regressieclaims te verwijderen of als legacy-compatibility te classificeren;
- legacy huishoudrollen niet-destructief te behouden maar buiten normale nieuwe roltoewijzing te houden;
- de expliciet in v2 genoemde bestaande functionele domeinen tegen de actuele permissiongrenzen te controleren;
- één gevonden runtimegap te sluiten: IP-owner-only system-sessies moeten de canonical IP-owner permission-union publiek projecteren zonder losse Superuser- of Platformbeheerderrollen te vereisen.

## 2. Canonical v2 rol- en contextmatrix

| Rol/account | Context | Huishoudrelatie | Platformauthority |
|---|---|---|---|
| Lid | `regular` | regulier huishouden | geen |
| Beheerder | `regular` | regulier huishouden | geen |
| Frontteamlid | `regular` | eigen regulier huishouden, `household.admin` | `platform.frontteam` |
| Superuser | `system` | systeemhuishouden 0 | exact `V2_SUPERUSER_TARGET_PERMISSIONS` |
| Platformbeheerder | `none` | geen huishouden | exact `PLATFORM_ADMIN_PERMISSIONS` |
| Superuser + Platformbeheerder | `system` | systeemhuishouden 0 | union Superuser-v2 + Platformbeheerder, zonder `platform.special_roles.manage` |
| IP-owner | `system` | systeemhuishouden 0 | Superuser-v2 + Platformbeheerder + `platform.special_roles.manage` |

`platform_roles` is geen publieke browserauthority en wordt niet in `/api/session` geprojecteerd.

## 3. Legacyrollen

Historische rollen zoals `household.viewer` en `household.advanced_member` blijven beschikbaar voor non-destructieve compatibility/migratie van bestaande data. Zij zijn geen nieuwe productrollen.

De normale household role mutation boundary accepteert uitsluitend:

- `household.member`;
- `household.admin`.

9.1.9 verwijdert legacy data niet en converteert bestaande rows niet destructief.

## 4. Bestaande functionele domeinen uit v2 sectie 8

### Meldingen / support

De actieve platformroutegrens gebruikt `platform.support_access.*`:

- Superuser: functioneel toegestaan;
- IP-owner: toegestaan;
- Platformbeheerder: niet vanwege de technische rol alleen;
- Frontteam: geen Superuser-supportbeheer.

### Externe bestanden / externe productbronnen

De actieve `/api/external-databases/*`-grens gebruikt:

- `platform.external_products.view`;
- `platform.external_products.search`;
- `platform.external_products.link_existing`.

Frontteam, Superuser en IP-owner bezitten deze functionele capabilities. Platformbeheerder niet.

### Centrale catalogus en universele artikelen

De functionele platformcataloguspermissions (`platform.catalog.*`) behoren tot Superuser-v2 en IP-owner, niet tot de technische Platformbeheerderrol.

### GPC

Functionele `platform.gpc.*`-rechten behoren tot Superuser-v2 en IP-owner. De afzonderlijke technische GPC-NL importactie blijft bewust achter `platform.technical_configuration.manage` en is daarmee Platformbeheerder/IP-owner-only.

### Externe databronconfiguratie

`platform.external_sources.view/manage` behoort tot Superuser-v2 en IP-owner. Dit verleent geen technische Platformbeheerderrechten en is gescheiden van de Frontteam `platform.external_products.*`-capabilities.

### Systeemhuishouden 0

H0 is uitsluitend `context_type=system`. Een vast e-mailadres verleent geen authority. Superuser en IP-owner krijgen system-context via actieve server-side platformrollen. Superuser+Platformbeheerder-stacking gebruikt dezelfde H0-context. Platformbeheerder-only blijft `none`.

### Authorization/session foundation

Server-side sessies blijven de identity/contextauthority. Platformpermissions worden live server-side geëvalueerd; role revocation werkt op de eerstvolgende request/sessionresolution. De publieke sessie projecteert permissions, geen raw platformrollen.

## 5. 9.1.9 runtimecorrectie: IP-owner public permission projection

Voor 9.1.9 kon een account met uitsluitend `platform.ip_owner` backend-routepermissions correct verkrijgen via de canonical evaluator, maar de publieke system-sessionpayload projecteerde niet automatisch `ROLE_PERMISSIONS["platform.ip_owner"]`.

De closure voegt daarom intern `is_ip_owner` toe aan `ServerSessionContext` en projecteert bij een IP-owner system-session exact de canonical IP-owner platformpermission-set. Dit:

- vereist geen extra `platform.superuser` of `platform.platform_admin` role rows;
- publiceert geen `platform_roles`;
- verandert geen householdauthority;
- houdt `platform.special_roles.manage` exclusief bij IP-owner.

## 6. Regressiebron na closure

Na succesvolle merge van 9.1.9 geldt:

1. `ROLLEN-EN-ACCOUNTMODEL-v2.0.md` is de functionele rollen-/accountbron van waarheid;
2. `AUTORISATIE-REGRESSIEPROTOCOL-v2.0.md` is het canonical regressieprotocol voor rollen-v2;
3. de dedicated workflow `Roles v2 9.1 acceptance closure validation` is de umbrella executable closuregate;
4. `authorization_matrix_acceptance.py` blijft bestaan als household/legacy-compatibility regressie en Superuser-v2 subcheck, maar is niet langer de volledige rollen-v2 bron van waarheid;
5. v1.1-documenten blijven uitsluitend als historische/compatibility referentie behouden.

## 7. Verplichte acceptance evidence

Een 9.1.9-kandidaat is alleen Ready wanneer op één exacte head groen zijn:

- dedicated roles-v2 acceptance closure workflow;
- server-side session security;
- Superuser-v2 permission cutover validation;
- Superuser + Platformbeheerder stacking validation;
- Frontteam personal household validation;
- Platform Authorizations/special-role regressies;
- authorization matrix compatibility gate;
- volledige frontendregressie;
- canonical release package;
- alle overige automatisch door de diff getriggerde regressies.

Daarnaast moeten compare/merge-base, filescope, reviews, reviewthreads en comments schoon zijn volgens de normale Rezzerv-governance.
