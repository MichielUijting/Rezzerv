# Rezzerv autorisatie-regressieprotocol v1.1

Status: **verplicht regressieonderdeel**

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
GO: alle 190 controles zijn conform matrix v1.1
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
- backendroutes controleren dezelfde permissie als de zichtbare frontendactie.

### Laag 3 — handmatige UI-steekproef

Test minimaal de volgende accounts/rollen:

| Rol | Controlepunten |
|---|---|
| Lid | geen Admin, geen Externe databases, Catalogus lezen, geen GPC-mutatie |
| Beheerder | Admin aanwezig, geen Externe databases, GPC-mutatie toegestaan, geen algemene Catalogusmutatie |
| Superuser | Admin, Externe databases, volledige Catalogus/GPC en platformrechten |
| Frontteamlid | Externe databases en frontteamrechten, geen impliciete platformrechten |

Controleer per rol:

1. zichtbaarheid van de tegel;
2. openen via normale navigatie;
3. directe URL;
4. zichtbaarheid/disabled-state van mutatieknoppen;
5. daadwerkelijke backendresponse bij een toegestane en verboden actie;
6. correcte 401/403-afhandeling;
7. behoud van het actieve huishouden in de header.

## Bewijsvoering

Een autorisatieregressie is pas afgerond wanneer beschikbaar zijn:

- console-uitvoer van de matrixacceptatietest;
- groene GitHub Actions-run `Authorization matrix acceptance`;
- resultaten van de sessie- en routeguards;
- screenshots of testnotities van de UI-steekproef;
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

- één van de 190 matrixcontroles faalt;
- een verboden tegel of knop zichtbaar is;
- een verboden route via een directe URL bereikbaar is;
- frontend en backend verschillende permissies hanteren;
- een beheerder platformrechten krijgt;
- een superuser geen Externe-databases-toegang heeft;
- een lid Admin of mutatierechten krijgt die in de matrix op Nee staan;
- een oude sessie of browseropslag autoriteit blijft geven.

## Relaties

Canonieke autorisatiedocumentatie:

```text
docs/security/AUTORISATIEMECHANISME-EN-MATRIX-v1.1.md
```

Uitvoerbare matrix:

```text
backend/app/testing/authorization_matrix_acceptance.py
```

CI-workflow:

```text
.github/workflows/authorization-matrix-acceptance.yml
```
