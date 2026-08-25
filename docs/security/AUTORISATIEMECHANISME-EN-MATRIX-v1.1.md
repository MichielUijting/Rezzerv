# Rezzerv autorisatiemechanisme en autorisatiematrix v1.1

Status: **historische/compatibility huishoudmatrix; niet langer de volledige platformrollen-bron van waarheid**.

Voor de actuele rollen-, account- en contextarchitectuur is `docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md` leidend. Voor de 9.1 acceptance closure en toekomstige rollen-v2 regressie is `docs/testing/AUTORISATIE-REGRESSIEPROTOCOL-v2.0.md` het canonical protocol. Dit v1.1-document blijft behouden voor non-destructieve household/legacy compatibility en de bestaande household-matrixregressie.

Vanaf 9.1.8a gebruikt `platform.superuser` de functionele v2-permissionset. Vanaf 9.1.8c is Superuser + Platformbeheerder stacking executable. IP-owner is een afzonderlijke protected rol met de union van Superuser-v2, Platformbeheerder en `platform.special_roles.manage`.

## 1. Doel

Deze documentatie legt de historische huishoudmatrix en de resterende compatibility-regressie vast. Zij mag niet meer zelfstandig worden gebruikt om actuele platformrollen, platformcontext of protected special-role authority af te leiden.

De uitvoerbare household compatibilitymatrix blijft nuttig voor bestaande huishoudfuncties. Platformauthority wordt canonical afgedekt door de v2 foundation, focused role/sessiongates en de 9.1 roles-v2 acceptance closure.

## 2. Autorisatiemechanisme

De browser is nooit de bron van waarheid voor identiteit, huishouden, rol of rechten.

De backend bepaalt bij ieder beveiligd verzoek opnieuw:

1. of de HttpOnly-sessiecookie geldig is;
2. welke gebruiker bij de sessie hoort;
3. welke actuele context (`regular`, `system` of `none`) geldt;
4. of een vereist lidmaatschap nog actief is;
5. welke actuele household- en/of platformrol server-side actief is;
6. welke actuele permissies daaruit volgen;
7. of het opgevraagde object binnen de toegestane scope valt.

### Fail-closed regels

- Geen geldige sessie: HTTP 401.
- Geen bevoegdheid of vereist lidmaatschap: HTTP 403.
- Een Bearer-token zonder geldige canonical sessie geeft geen autoriteit.
- Geen automatische fallback naar huishouden `0`.
- Huishouden `0` is `context_type=system` en vereist een actieve server-side systeemrol (`platform.superuser` of `platform.ip_owner`); een e-mailadres alleen verleent geen authority.
- Platformbeheerder-only gebruikt `context_type=none`.
- Superuser + Platformbeheerder gebruikt na 9.1.8c één H0/system-context met de union van beide permission-sets.
- Frontendvelden zoals `role`, `household_id` en `permissions` zijn niet autoritatief.
- Raw `platform_roles` worden niet als browserauthority gepubliceerd.

## 3. Rollen in deze compatibilitymatrix

### Lid

Heeft toegang tot de reguliere huishoudfuncties die in de matrix met **Ja** zijn gemarkeerd.

### Beheerder

Erft alle toegestane ledenrechten en krijgt aanvullende huishoudbeheerrechten. Een Beheerder heeft geen platformrechten alleen vanwege deze rol.

### Superuser

Gebruikt systeemhuishouden `0` als system-context en krijgt vanaf 9.1.8a exact de actieve functionele Superuser-v2-set (`ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS` / `V2_SUPERUSER_TARGET_PERMISSIONS`). De historische vaste Superuser-e-mail kan als gereserveerde identityreferentie bestaan, maar verleent geen authority zonder de actieve platformrol.

De gewone Superuser heeft **geen technische Platformbeheerderrechten**. Rechten zoals `platform.sessions.revoke`, `platform.users.suspend`, `platform.audit.view`, `platform.permissions.manage`, `platform.feature_flags.manage` en de overige technische Platformbeheerderpermissions vereisen de aparte Platformbeheerderrol. `platform.special_roles.manage` hoort uitsluitend bij IP-owner.

Na 9.1.8c mag hetzelfde account Superuser en Platformbeheerder combineren. Dat account gebruikt H0/system-context en krijgt de exacte union zonder IP-owner-only special-role authority.

### Frontteamlid

De actieve v2-constructie is een eigen regulier huishouden met `household.admin` plus de afzonderlijke platformrol `platform.frontteam`. Historische `household.frontteam`-data blijft compatibilitydata en is geen nieuwe platformauthoritybron.

## 4. Matrix v1.1 — compatibilitykern

De uitvoerbare householdmatrix staat in:

- `backend/app/testing/authorization_matrix_acceptance.py`

Belangrijke historische/household onderscheidingen:

| Functie | Lid | Beheerder | Superuser/H0 | Frontteam compatibility |
|---|---:|---:|---:|---:|
| Admin/householdbeheer | Nee | Ja | Ja | Ja |
| Externe databases | Nee | Nee | Ja | Ja |
| Catalogus bekijken | Ja | Ja | Ja | Ja |
| Catalogus wijzigen | Nee | Nee | Ja | Ja |
| Catalogus beheren | Nee | Nee | Ja | Ja |
| GPC bekijken | Ja | Ja | Ja | Ja |
| GPC wijzigen | Nee | Ja | Ja | Ja |
| GPC beheren | Nee | Ja | Ja | Ja |
| Technisch Platformbeheer | Nee | Nee | alleen met aparte Platformbeheerderrol | Nee |

Deze tabel is geen volledige v2-platformmatrix. Platformbeheerder, stacking en IP-owner worden canonical in de v2 acceptance closure getoetst.

## 5. Automatische compatibility-regressietest

De historische householdmatrix wordt gecontroleerd door:

```text
backend/app/testing/authorization_matrix_acceptance.py
```

De test voert momenteel 192 controles uit:

- 45 functionele householdrechten × 4 compatibilityrollen;
- 12 extra structuur-/risicocontroles waaronder de actuele Superuser-v2 separation.

Een geldige run eindigt met:

```text
GO: alle 192 controles zijn conform household-matrix v1.1 + Superuser-v2
AUTORISATIEMATRIX_ACCEPTATIE_GREEN
```

Deze marker is na 9.1.9 **een vereiste subgate, maar niet zelfstandig voldoende voor volledige rollen-v2 acceptatie**.

## 6. Lokale uitvoering

Vanuit de repository-root:

```powershell
.\RUN_AUTORISATIEMATRIX_TEST.bat
```

Het startbestand bouwt/ververst de backendruntime en voert de compatibilitymatrix uit.

## 7. CI-regressiegate

GitHub Actions-workflow:

```text
.github/workflows/authorization-matrix-acceptance.yml
```

De volledige rollen-v2 umbrella acceptance staat aanvullend in:

```text
.github/workflows/roles-v2-acceptance-closure.yml
```

## 8. UI-steekproef

De household compatibilitymatrix alleen bewijst geen volledige v2-UI. Voor rollen-v2 geldt het v2-regressieprotocol. Waar handmatige controle nodig is, test minimaal:

1. Lid — reguliere householdroutes, geen platformauthority;
2. Beheerder — householdbeheer, geen platformauthority;
3. Frontteam — eigen regulier huishouden plus beperkte Frontteam-capabilities;
4. Superuser — H0 plus functionele v2-capabilities, geen technische rechten zonder stacking;
5. Platformbeheerder — `none` plus technische platformroutes, geen householdfallback;
6. Superuser + Platformbeheerder — H0 plus permission-union;
7. IP-owner — protected union inclusief special-role management.

Controleer per actor directe route, zichtbaarheid, backendresponse, 401/403-semantiek en actuele context.

## 9. Wijzigingsbeheer

Een wijziging in rollen-v2 autorisatie is pas compleet wanneer doelcontract, permissionregistratie, sessie/context, backendguards, frontendguards, executable regressies en documentatie gezamenlijk zijn bijgewerkt.

Hardgecodeerde e-mail-, household-0-, Bearer- of browserfallbacks mogen geen nieuwe authority introduceren.
