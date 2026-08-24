# Superuser-v2 permission cutover — 9.1.8a

## Status

9.1.8a activeert de reeds bestaande `V2_SUPERUSER_TARGET_PERMISSIONS` als de canonical runtime grantset voor `platform.superuser`.

De cutover verandert geen rolidentiteit en introduceert geen nieuwe permission keys. De bestaande rol `platform.superuser` blijft de functionele Superuser-identiteit; alleen de aan die rol gekoppelde platformpermissions worden gecontroleerd omgezet van de historische v1.1-set naar de v2-doelset.

## Canonical authority na 9.1.8a

`ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS` is exact gelijk aan `V2_SUPERUSER_TARGET_PERMISSIONS`.

De Superuser-v2-set bevat functionele platformauthority voor onder meer:

- huishoudmetadata en supporttoegang;
- systeemhuishoudtoegang;
- Frontteam-berichten en polls;
- externe producten;
- platformcatalogus en GPC;
- externe bronnen.

De gewone Superuser krijgt expliciet **geen** technische Platformbeheerderauthority. De volledige `PLATFORM_ADMIN_PERMISSIONS`-set blijft uitsluitend een afzonderlijk technisch domein.

Daarmee heeft een gewone Superuser onder andere niet automatisch:

- `platform.sessions.revoke`;
- `platform.users.suspend`;
- `platform.permissions.manage`;
- `platform.feature_flags.manage`;
- `platform.audit.view`;
- `platform.logs.view`;
- `platform.diagnostics.view`;
- technische configuratie-, recovery-, fixture-, integration- of background-job authority.

Ook `platform.special_roles.manage` blijft afwezig bij de gewone Superuser.

## IP-owner grens

`platform.ip_owner` blijft de beschermde union van:

1. `V2_SUPERUSER_TARGET_PERMISSIONS`;
2. `PLATFORM_ADMIN_PERMISSIONS`;
3. `platform.special_roles.manage`.

9.1.8a verandert die grens niet en voegt geen special-role mutatie-API toe.

## Runtime en bestaande accounts

`ensure_authorization_foundation()` reseedt `auth_role_permissions` vanuit de canonical rolmatrix. Daardoor krijgt ook een reeds bestaande actieve `platform.superuser` na foundation-initialisatie exact de v2-grantset. Stale v1.1-technische grants worden verwijderd; de platformroltoekenning aan de gebruiker zelf blijft behouden.

Publieke system-session payloads voor een actieve Superuser projecteren dezelfde v2-platformpermissions, naast de bestaande systeemhuishoudrolpermissions. Er wordt geen `platform_roles`-array aan de browser blootgesteld en er ontstaat geen household/H0 fallback.

## Compatibility alias

`ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS` blijft tijdelijk bestaan voor oudere regression-imports. Vanaf 9.1.8a is dit uitsluitend een gedeprécieerde alias naar `ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS`; het is geen afzonderlijke authoritybron en vertegenwoordigt niet langer een actieve v1.1-runtime.

Nieuwe code en nieuwe tests moeten `ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS` gebruiken.

## Bewust buiten scope

9.1.8a doet **niet**:

- Superusers, Frontteamleden of Platformbeheerders aanstellen of intrekken;
- `platform.special_roles.manage` beschikbaar maken aan een gewone Superuser;
- de IP-owner management-API implementeren;
- de huidige sessieregels voor gestapelde platformrollen wijzigen;
- household/H0 authority toevoegen;
- nieuwe platformpermissions creëren;
- Platformbeheerderpermissions wijzigen.

De controlled IP-owner special-role management cutover volgt afzonderlijk in **9.1.8b**.

## Acceptance

De focused workflow `Superuser v2 permission cutover validation` moet eindigen met:

`SUPERUSER_V2_9_1_8A_PERMISSION_CUTOVER_GREEN`

Daarnaast blijven de bestaande authorization foundation-, Platformbeheerder closure-, volledige frontendregressie- en release-package-gates beslissend vóór Ready en merge.
