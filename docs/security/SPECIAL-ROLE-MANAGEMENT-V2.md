# 9.1.8b — Special-role management door de IP-eigenaar

Status: afgeronde v2 special-role management authority; 9.1.8c voert de eerder gereserveerde stackingcutover uit.

## Doel

De beschermde IP-eigenaar beheert `platform.superuser` en `platform.platform_admin`. De aanvullende rol `platform.frontteam` mag daarnaast ook door een Superuser worden toegekend of ingetrokken.

De canonical mutatiepermissions zijn:

- `platform.special_roles.manage` voor IP-owner-only beheer van Superuser en Platformbeheerder;
- `platform.frontteam_roles.manage` voor Frontteambeheer door Superuser en IP-eigenaar.

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

## Frontteam lifecycle

Frontteam is een aanvullende platformrol bovenop een reguliere gebruikerscontext. Heeft de gebruiker al een eigen regulier huishouden, dan blijven dat huishouden en de bestaande huishoudrol ongewijzigd. Alleen wanneer nog geen regulier huishouden bestaat, mag de bestaande canonical Frontteam-provisioning een persoonlijk regulier huishouden aanmaken.

Frontteam blijft onverenigbaar met systeem- en Platformbeheerderrollen.

De revoke/regrant-lifecycle wordt in 9.1.8b volledig gesloten:

- canonical Frontteam-revoke deactiveert uitsluitend `platform.frontteam` en verwijdert de actieve Frontteam→persoonlijk-huishouden mapping;
- het persoonlijke huishouden zelf blijft bestaan met exact dezelfde ID en `context_type=regular`;
- het bestaande reguliere household membership en `household.admin` blijven actief;
- bestaande en nieuwe sessies op dat huishouden worden na revoke als gewone reguliere household-sessies opgelost, zonder Frontteam-platformpermissions;
- regrant herstelt de Frontteam-mapping deterministisch naar exact dezelfde household-ID en maakt geen tweede huishouden of membership aan;
- direct/stale database-deactivatie buiten de canonical revoke-flow krijgt deze transitie niet en blijft via de bestaande sessiecontracts fail-closed.

Daarmee wordt de persoonlijke household-data niet weggegooid wanneer iemand tijdelijk geen Frontteamlid meer is, terwijl Frontteamauthority zelf direct verdwijnt.

## Vervolg 9.1.8c

De tijdelijke 9.1.8b-blokkade op `platform.superuser` + `platform.platform_admin` wordt in 9.1.8c gecontroleerd opgeheven nadat de gecombineerde session/account-context executable is gemaakt.

Het v2-doelmodel is:

- Superuser + Platformbeheerder mag op één account worden gecombineerd;
- de combinatie gebruikt H0 / `context_type=system`, omdat Superuser H0 verleent;
- technische Platformbeheerderpermissions worden in dezelfde sessie toegevoegd;
- Frontteamconflicten en IP-owner + Platformbeheerder blijven fail-closed;
- de browser krijgt geen `platform_roles`-authorityprojectie.

Het executable contract en de revoke-transities staan in `SUPERUSER-PLATFORM-ADMIN-STACKING-CUTOVER.md`.

## Acceptatie 9.1.8b

De gemergde 9.1.8b-kandidaat bewees:

1. exact permission split: inventory versus mutation;
2. IP-owner-only special-role mutation;
3. protected IP-owner invariant;
4. safe server-generated role actions;
5. de tijdelijke stackinggrens bleef fail-closed tot de aparte 9.1.8c-cutover;
6. Frontteam revoke/regrant behoudt exact hetzelfde reguliere huishouden en membership;
7. Frontteamauthority verdwijnt direct na revoke en keert pas terug na regrant;
8. bestaande server-session fail-closed contracts;
9. Platformautorisaties Playwright regression;
10. production frontend build;
11. volledige canonical frontend regression;
12. canonical release package.


## Frontteamledenadministratie

De Frontteambeheerfunctie werkt op bestaande Inhuis-accounts. Een Superuser of IP-eigenaar voegt een gebruiker toe op exact e-mailadres. Alleen geregistreerde Frontteamleden worden in de beheerweergave getoond.

Een Frontteamregistratie kent twee toestanden:
- `active`: de aanvullende platformrol `platform.frontteam` is actief;
- `inactive`: de gebruiker blijft als Frontteamlid geregistreerd, maar de aanvullende Frontteambevoegdheden zijn uitgeschakeld.

Activeren en deactiveren wijzigen uitsluitend de Frontteambevoegdheid. Verwijderen verwijdert de Frontteamregistratie. Geen van deze acties verwijdert het Inhuis-account, het reguliere huishouden of de bestaande huishoudrol.
