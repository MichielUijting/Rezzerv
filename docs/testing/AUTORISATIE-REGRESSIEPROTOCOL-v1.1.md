# Rezzerv autorisatie-regressieprotocol v1.1

Status: **historisch compatibility-protocol voor de householdmatrix; niet langer het volledige rollen-v2 regressieprotocol**.

Het canonical rollen-v2 protocol staat in `docs/testing/AUTORISATIE-REGRESSIEPROTOCOL-v2.0.md`. Dit v1.1-protocol blijft behouden omdat de householdmatrix en oude compatibilitygevallen nog regressiewaarde hebben. Bij een conflict over platformrollen, contexten of protected authority is v2 leidend.

## Doel

Dit protocol bewaakt de bestaande household compatibilitymatrix en voorkomt regressies in de historische householdrechten die nog onderdeel zijn van de actuele runtime.

Het protocol is na 9.1.9 een **subgate** van rollen-v2 acceptance. Het beschrijft niet zelfstandig Platformbeheerder, Superuser+Platformbeheerder-stacking of IP-owner.

## Verplichte regressielagen

### Laag 1 — household matrixacceptatie

Uitvoerbaar met:

```powershell
.\RUN_AUTORISATIEMATRIX_TEST.bat
```

Acceptatiecriterium:

```text
GO: alle 192 controles zijn conform household-matrix v1.1 + Superuser-v2
AUTORISATIEMATRIX_ACCEPTATIE_GREEN
```

Iedere andere uitkomst is NO-GO voor deze compatibilitylaag.

### Laag 2 — sessie- en routebeveiliging

De bestaande regressiegates moeten bevestigen:

- alleen een geldige HttpOnly-sessiecookie geeft canonical runtimeauthority;
- een Bearer-token zonder geldige sessie verleent geen authority;
- een huishoudmismatch faalt gesloten;
- huishouden `0` is geen fallback en vereist een actieve server-side systeemrol;
- een e-mailadres alleen verleent geen H0/Superuserauthority;
- directe URL-toegang omzeilt geen frontendguard;
- backendroutes controleren de vereiste canonical permission;
- Superuser-v2 krijgt zijn functionele platformset maar geen technische Platformbeheerderpermissions;
- `platform.special_roles.manage` blijft buiten de gewone Superuser-set.

Voor `none`, stacking en IP-owner gelden aanvullend de v2 closurecontracts.

### Laag 3 — UI-steekproef

De historische householdsteekproef kan minimaal Lid, Beheerder, Superuser/H0 en Frontteam omvatten. Voor een volledige actuele rollen-v2 steekproef moeten ook Platformbeheerder, Superuser+Platformbeheerder en IP-owner worden meegenomen volgens het v2-regressieprotocol.

Controleer waar van toepassing:

1. zichtbaarheid van de tegel;
2. openen via normale navigatie;
3. directe URL;
4. zichtbaarheid/disabled-state van mutatieknoppen;
5. daadwerkelijke backendresponse bij toegestane en verboden actie;
6. correcte 401/403-afhandeling;
7. behoud van de server-side vastgestelde context.

## Bewijsvoering

Deze compatibilitylaag is groen wanneer beschikbaar zijn:

- console-uitvoer van de household matrixacceptatietest;
- groene GitHub Actions-run `Authorization matrix acceptance`;
- resultaten van de relevante sessie-/routeguards;
- branch en exact commit-SHA.

Voor volledige 9.1/v2-acceptatie zijn aanvullend de dedicated roles-v2 closuregate, focused role/sessiongates, full frontend regression en canonical release package verplicht.

## Triggers voor hertest

Deze compatibilitylaag moet opnieuw worden uitgevoerd bij wijzigingen aan householdrollen/permissies, sessiepayload/context, routeguards, Catalogus/GPC/Admin householdgedrag, lidmaatschappen of relevante testprovisioning.

Een volledige rollen-v2 hertest volgt de ruimere triggerlijst uit `AUTORISATIE-REGRESSIEPROTOCOL-v2.0.md`.

## NO-GO-criteria

NO-GO voor deze laag geldt onder meer wanneer:

- één van de 192 compatibilitycontroles faalt;
- een verboden householdtegel/actie bereikbaar wordt;
- frontend en backend verschillende householdpermissions hanteren;
- een Beheerder platformauthority krijgt;
- een gewone Superuser technische Platformbeheerderpermissions of `platform.special_roles.manage` krijgt;
- een oude sessie of browseropslag authority blijft geven.

## Relaties

Historische householdmatrix:

```text
docs/security/AUTORISATIEMECHANISME-EN-MATRIX-v1.1.md
```

Canonical rollen-v2 doelcontract:

```text
docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md
```

Canonical rollen-v2 regressieprotocol:

```text
docs/testing/AUTORISATIE-REGRESSIEPROTOCOL-v2.0.md
```

Uitvoerbare household compatibilitymatrix:

```text
backend/app/testing/authorization_matrix_acceptance.py
```

Umbrella v2 closure:

```text
.github/workflows/roles-v2-acceptance-closure.yml
```
