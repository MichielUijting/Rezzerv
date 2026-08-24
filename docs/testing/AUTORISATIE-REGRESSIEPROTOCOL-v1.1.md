# Rezzerv autorisatie-regressieprotocol v1.1

Status: **verplicht regressieonderdeel voor huishoudmatrix v1.1 + Superuser-v2 platformoverlay**

De huishoudmatrix v1.1 blijft de regressiebaseline voor bestaande huishoudfuncties. Het PO-goedgekeurde rollen- en accountdoelcontract staat in `docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md`. Vanaf 9.1.8a is de functionele Superuser-v2 platformauthority actief en is technische Platformbeheerderauthority daarvan expliciet gescheiden.

## Doel

Dit protocol voorkomt dat wijzigingen aan login, sessies, rollen, schermen of routes ongemerkt autorisaties verruimen of beperken.

## Verplichte regressielagen

### Laag 1 — matrixacceptatie

Uitvoerbaar met:

```powershell
.\RUN_AUTORISATIEMATRIX_TEST.bat
```

Acceptatiecriterium:

```text
GO: alle 192 controles zijn conform household-matrix v1.1 + Superuser-v2
AUTORISATIEMATRIX_ACCEPTATIE_GREEN
```

Iedere andere uitkomst is NO-GO.

### Laag 2 — sessie- en routebeveiliging

De bestaande regressiegates moeten bevestigen:

- alleen een geldige HttpOnly-sessiecookie geeft runtimeautoriteit;
- een Bearer-token zonder geldige sessie faalt met 401;
- een huishoudmismatch faalt met 403;
- huishouden `0` is alleen bereikbaar voor de canonieke superuser;
- directe URL-toegang omzeilt geen frontendguard;
- backendroutes controleren dezelfde permissie als de zichtbare frontendactie;
- Superuser-v2 krijgt zijn functionele platformset maar geen technische Platformbeheerderpermissions;
- `platform.special_roles.manage` blijft buiten de gewone Superuser-set.

### Laag 3 — handmatige UI-steekproef

Test minimaal de volgende accounts/rollen:

| Rol | Controlepunten |
|---|---|
| Lid | geen Admin, geen Externe databases, Catalogus lezen, geen GPC-mutatie |
| Beheerder | Admin aanwezig, geen Externe databases, GPC-mutatie toegestaan, geen algemene Catalogusmutatie |
| Superuser | Admin voor huishoudbeheer, Externe databases, volledige functionele Catalogus/GPC; geen technische Platformbeheerderauthority zonder afzonderlijke rol |
| Frontteamlid | Externe databases en Frontteamrechten, geen impliciete technische platformrechten |

Controleer per rol:

1. zichtbaarheid van de tegel;
2. openen via normale navigatie;
3. directe URL;
4. zichtbaarheid/disabled-state van mutatieknoppen;
5. daadwerkelijke backendresponse bij een toegestane en verboden actie;
6. correcte 401/403-afhandeling;
7. behoud van de actieve context in de header.

## Bewijsvoering

Een autorisatieregressie is pas afgerond wanneer beschikbaar zijn:

- console-uitvoer van de matrixacceptatietest;
- groene GitHub Actions-run `Authorization matrix acceptance`;
- resultaten van de sessie- en routeguards;
- resultaten van de Superuser-v2 focused cutover-gate wanneer platformauthority wijzigt;
- screenshots of testnotities van de UI-steekproef waar van toepassing;
- vermelding van branch en commit-SHA;
- expliciet PO-oordeel GO of NO-GO.

## Triggers voor verplichte hertest

De volledige autorisatieregressie moet opnieuw worden uitgevoerd bij wijzigingen aan:

- rollen of permissies;
- login, logout of sessiepayload;
- actieve huishoudcontext;
- routeguards;
- starttegels of navigatie;
- Catalogus, GPC, Admin of Externe databases;
- platformbeheer;
- lidmaatschappen of permissie-overrides;
- databaseprovisioning van testaccounts;
- frontend- of backendcode die 401/403 verwerkt.

## NO-GO-criteria

NO-GO geldt onder meer wanneer:

- één van de 192 matrixcontroles faalt;
- een verboden tegel of knop zichtbaar is;
- een verboden route via een directe URL bereikbaar is;
- frontend en backend verschillende permissies hanteren;
- een beheerder platformrechten krijgt;
- een gewone Superuser een technische Platformbeheerderpermission krijgt;
- een gewone Superuser `platform.special_roles.manage` krijgt;
- een Superuser-v2 zijn functionele Externe-databasesrechten mist;
- een lid Admin of mutatierechten krijgt die in de matrix op Nee staan;
- een oude sessie of browseropslag autoriteit blijft geven.

## Relaties

Canonieke huishoudmatrix plus actieve Superuser-v2 overlay:

```text
docs/security/AUTORISATIEMECHANISME-EN-MATRIX-v1.1.md
```

Rollen-v2 doelcontract:

```text
docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md
```

Uitvoerbare matrix:

```text
backend/app/testing/authorization_matrix_acceptance.py
```

CI-workflows:

```text
.github/workflows/authorization-matrix-acceptance.yml
.github/workflows/superuser-v2-permission-cutover.yml
```
