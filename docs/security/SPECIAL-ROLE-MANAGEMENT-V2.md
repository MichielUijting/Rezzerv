# 9.1.8b — Special-role management door de IP-eigenaar

Status: implementatieslice voor de v2 special-role management authority.

## Doel

Alleen de beschermde IP-eigenaar mag de gewone speciale platformrollen aanstellen of intrekken:

- `platform.superuser`;
- `platform.frontteam`;
- `platform.platform_admin`.

De canonical mutatiepermission is exact:

`platform.special_roles.manage`

De bestaande inventarisatiepermission blijft afzonderlijk:

`platform.permissions.manage`

Een gewone Platformbeheerder mag de platformautorisatie-inventaris dus bekijken, maar kan geen speciale rol muteren.

## Authority

De backend blijft de enige bron van waarheid. Speciale rollen worden uitsluitend opgeslagen in `auth_platform_user_roles`.

- IP-owner is beschermd en niet muteerbaar via deze flow.
- Superuser, Frontteamlid en Platformbeheerder zijn de enige beheerbare rollen.
- Een geschorst account kan geen nieuwe speciale rol krijgen.
- Een bestaande speciale rol kan defensief worden ingetrokken.
- Iedere mutatie wordt geschreven naar de bestaande authorization audit met `reason=platform.special_roles.manage`.
- Householdcontext, H0-fallback, bearer authority en admin-key authority zijn geen onderdeel van deze beheerflow.

## Frontteam

Een Frontteam-grant gebruikt de bestaande canonical Frontteam-provisioning en creëert of hergebruikt het deterministische persoonlijke reguliere huishouden met `household.admin`.

Frontteam is onverenigbaar met systeem- en Platformbeheerderrollen. Een eerste Frontteam-grant wordt geweigerd wanneer het doelaccount al unrelated reguliere huishoudlidmaatschappen heeft.

## Gecontroleerde vervolgslice 9.1.8c

De v2-doelarchitectuur staat toe dat `platform.superuser` en `platform.platform_admin` op één account worden gecombineerd. De huidige server-session runtime modelleert die combinatie nog als incompatibele accountcontext.

Die accountcontextwijziging wordt bewust niet stil in dezelfde authority-slice uitgevoerd. **9.1.8c** wordt de afzonderlijke session/account-context cutover voor role stacking en de volledige post-revoke Frontteam-contexttransitie.

Tot die cutover Ready is, mag 9.1.8b geen samengestelde runtime-state introduceren die de bestaande sessielaag niet kan oplossen. De focused 9.1.8b-gate draait daarom ook de bestaande server-session- en Frontteam-provisioningcontracts.

## Acceptatie 9.1.8b

Voor Ready moeten op één exacte PR-head aantoonbaar groen zijn:

1. exact permission split: inventory versus mutation;
2. IP-owner-only special-role mutation;
3. protected IP-owner invariant;
4. safe server-generated role actions;
5. Frontteam provisioning/lifecycle contract;
6. bestaande server-session fail-closed contracts;
7. Platformautorisaties Playwright regression;
8. production frontend build;
9. volledige canonical frontend regression;
10. canonical release package.

Geen merge zolang één van deze grenzen rood of inhoudelijk onbeslist is.
