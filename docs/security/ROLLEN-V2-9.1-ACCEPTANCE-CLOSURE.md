# Rollen- en accountmodel v2 — 9.1 acceptance closure

Status: **9.1.9 acceptance candidate**. Dit document sluit geen PR zelfstandig; de exacte kandidaat-head moet alle genoemde executable gates groen doorlopen voordat 9.1 als afgerond mag worden beschouwd.

## 1. Doel

9.1.9 voegt geen nieuwe productfunctionaliteit toe. De tranche sluit de overgang van het historische v1.1-autorisatiecontract naar het PO-goedgekeurde `ROLLEN-EN-ACCOUNTMODEL-v2.0.md` door:

- het geïmplementeerde rollen-/account-/contextmodel als één geheel executable te bewijzen;
- resterende transitional regressieclaims te verwijderen of als legacy-compatibility te classificeren;
- legacy huishoudrollen niet-destructief te behouden maar buiten normale nieuwe roltoewijzing te houden;
- de expliciet in v2 genoemde bestaande functionele domeinen tegen de actuele permissiongrenzen te controleren;
- de actuele PO-beslissing over IP-owner te borgen:
  - IP-owner gebruikt geen systeemhuishouden 0 en geen functionele/technische platformcontext;
  - IP-owner krijgt uitsluitend een none-context met `platform.special_roles.manage` voor Superuserbeheer.

## 2. Canonical v2 rol- en contextmatrix

| Rol/account | Context | Huishoudrelatie | Platformauthority |
|---|---|---|---|
| Lid | `regular` | regulier huishouden | geen |
| Beheerder | `regular` | regulier huishouden | geen |
| Frontteamlid | `regular` | eigen regulier huishouden, `household.admin` | `platform.frontteam` |
| Superuser | `system` | systeemhuishouden 0 | exact `V2_SUPERUSER_TARGET_PERMISSIONS` |
| Platformbeheerder | `none` | geen huishouden | exact `PLATFORM_ADMIN_PERMISSIONS` |
| Superuser + Platformbeheerder | `system` | systeemhuishouden 0 | union Superuser-v2 + Platformbeheerder, zonder `platform.special_roles.manage` |
| IP-owner | `none` | geen huishouden | uitsluitend `platform.special_roles.manage` voor Superuserbeheer |

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
- IP-owner: niet toegestaan;
- Platformbeheerder: niet vanwege de technische rol alleen;
- Frontteam: geen Superuser-supportbeheer.

### Externe bestanden / externe productbronnen

De actieve `/api/external-databases/*`-grens gebruikt:

- `platform.external_products.view`;
- `platform.external_products.search`;
- `platform.external_products.link_existing`.

Frontteam en Superuser bezitten deze functionele capabilities. Platformbeheerder en IP-owner niet.

### Centrale catalogus en universele artikelen

De functionele platformcataloguspermissions (`platform.catalog.*`) behoren tot Superuser-v2, niet tot Platformbeheerder of IP-owner.

### GPC

Functionele `platform.gpc.*`-rechten behoren tot Superuser-v2. De afzonderlijke technische GPC-NL importactie blijft achter `platform.technical_configuration.manage` en is daarmee Platformbeheerder-only.

### Externe databronconfiguratie

`platform.external_sources.view/manage` behoort tot Superuser-v2. IP-owner krijgt deze functionele bronconfiguratie niet. Dit is gescheiden van de Frontteam `platform.external_products.*`-capabilities.

### Systeemhuishouden 0

H0 is uitsluitend `context_type=system`. Een vast e-mailadres verleent geen authority. Superuser krijgt system-context via de actieve server-side Superuserrol. Superuser+Platformbeheerder-stacking gebruikt dezelfde H0-context. Platformbeheerder-only en IP-owner blijven `none`; IP-owner heeft geen H0-toegang.

### Authorization/session foundation

Server-side sessies blijven de identity/contextauthority. Platformpermissions worden live server-side geëvalueerd; role revocation werkt op de eerstvolgende request/sessionresolution. De publieke sessie projecteert permissions, geen raw platformrollen.

## 5. 9.1.9 runtimecorrecties

### 5.1 IP-owner none-context en minimale permissionprojectie

De actuele PO-beslissing maakt IP-owner expliciet geen operationele platformrol. Een account met uitsluitend `platform.ip_owner`:

- gebruikt `context_type=none`;
- heeft geen actief huishouden en geen toegang tot systeemhuishouden 0;
- projecteert exact `{"platform.special_roles.manage"}`;
- publiceert geen `platform_roles`;
- erft geen Superuser- of Platformbeheerderpermissions.

### 5.2 Aparte IP-owner UI-boundary

De IP-owner krijgt geen functionele Superuser-UI. De frontend toont een eigen eenvoudige landing met uitsluitend **Superusers** en **Uitloggen**. De aparte Superuserbeheerpagina:

- toont alleen de gegevens die nodig zijn om Superuserstatus te beheren;
- laat alleen `platform.superuser` toekennen of intrekken;
- toont geen Frontteam- of Platformbeheerdermutaties;
- blijft server-side beschermd door `platform.special_roles.manage`.

Directe Platformbeheerdermutaties via de voormalige special-role route worden geweigerd. Frontteambeheer blijft achter de afzonderlijke Superuserbevoegdheid.

## 6. Regressiebron na closure

Na succesvolle merge van 9.1.9 geldt:

1. `ROLLEN-EN-ACCOUNTMODEL-v2.0.md` is de functionele rollen-/accountbron van waarheid;
2. `AUTORISATIE-REGRESSIEPROTOCOL-v2.0.md` is het canonical regressieprotocol voor rollen-v2;
3. de dedicated workflow `Roles v2 9.1 acceptance closure validation` is de umbrella executable closuregate;
4. `authorization_matrix_acceptance.py` blijft bestaan als household/legacy-compatibility regressie en Superuser-v2 subcheck, maar is niet langer de volledige rollen-v2 bron van waarheid;
5. v1.1-documenten blijven uitsluitend als historische/compatibility referentie behouden.

## 7. Verplichte acceptance evidence

Een 9.1.9-kandidaat is alleen Ready wanneer op één exacte head groen zijn:

- dedicated roles-v2 acceptance closure workflow, inclusief de directe frontend system-capability boundarytest;
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
