# Rezzerv autorisatiemechanisme en autorisatiematrix v1.1

Status: **canonieke huishoudmatrix v1.1 met actieve Superuser-v2 platformoverlay**

Overgangsstatus: de huishoudmatrix v1.1 blijft de regressiebaseline voor de
bestaande huishoudrollen. Het PO-goedgekeurde rollen- en accountdoelcontract
staat in `docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md`. Met 9.1.8a is de
platformauthority van `platform.superuser` bewust naar de v2-doelset
omgezet. Technische Platformbeheerderauthority is sindsdien een afzonderlijk
domein en is niet langer impliciet onderdeel van Superuser.

## 1. Doel

Deze documentatie legt vast:

- hoe Rezzerv authenticatie en autorisatie uitvoert;
- welke rollen bestaan;
- welke rechten per rol gelden;
- hoe de huishoudmatrix v1.1 en de actieve Superuser-v2 overlay automatisch en handmatig worden getest;
- welke regressiegates verplicht groen moeten zijn.

De huishoudmatrix v1.1 blijft leidend voor de bestaande huishoudfuncties. Voor platformauthority van de Superuser is vanaf 9.1.8a de v2-grens leidend.

## 2. Autorisatiemechanisme

De browser is nooit de bron van waarheid voor identiteit, huishouden, rol of rechten.

De backend bepaalt bij ieder beveiligd verzoek opnieuw:

1. of de HttpOnly-sessiecookie geldig is;
2. welke gebruiker bij de sessie hoort;
3. welk huishouden actief is;
4. of het lidmaatschap nog actief is;
5. welke actuele rol bij dat lidmaatschap hoort;
6. welke huishoud- en platformpermissies bij die rol horen;
7. of het opgevraagde object binnen het actieve huishouden valt.

### Fail-closed regels

- Geen geldige sessie: HTTP 401.
- Geen bevoegdheid of geen lidmaatschap: HTTP 403.
- Een Bearer-token zonder geldige sessiecookie geeft geen autoriteit.
- Geen automatische fallback naar huishouden `0`.
- Huishouden `0` is uitsluitend toegankelijk voor `supergebruiker@rezzerv.local` met rol `owner`.
- Frontendvelden zoals `role`, `household_id` en `permissions` zijn niet autoritatief.
- De frontend gebruikt de publieke payload van `GET /api/session` uitsluitend voor weergave en routekeuzes; de backend blijft beslissend.

## 3. Rollen

### Lid

Heeft toegang tot de reguliere huishoudfuncties die in de matrix met **Ja** zijn gemarkeerd.

### Beheerder

Erft alle toegestane ledenrechten en krijgt de aanvullende huishoudbeheerrechten uit de matrix. Een beheerder heeft geen platformrechten alleen vanwege deze rol.

### Superuser

Erft de toegestane beheerder- en ledenrechten en heeft toegang tot systeemhuishouden `0`. De canonieke identiteit is `supergebruiker@rezzerv.local`.

Voor platformauthority gebruikt de Superuser vanaf 9.1.8a exact de actieve functionele Superuser-v2-set (`ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS` / `V2_SUPERUSER_TARGET_PERMISSIONS`). Daaronder vallen onder meer supporttoegang, systeemhuishoudtoegang, Frontteam-berichten en polls, externe producten, platformcatalogus/GPC en externe bronnen.

De gewone Superuser heeft **geen technische Platformbeheerderrechten**. Rechten zoals `platform.sessions.revoke`, `platform.users.suspend`, `platform.audit.view`, `platform.permissions.manage`, `platform.feature_flags.manage` en de overige technische Platformbeheerderpermissions vereisen een afzonderlijke Platformbeheerderrol. Ook `platform.special_roles.manage` hoort niet bij de gewone Superuser.

De Superuser heeft wel volledige functionele toegang tot **Externe databases** voor de v2-rechten view/search/link-existing.

### Frontteamlid

Is een afzonderlijke rol met de rechten die in de kolom **Frontteamlid** met **Ja** zijn gemarkeerd. Een frontteamlid heeft volledige toegang tot **Externe databases** binnen de Frontteampermission-set.

## 4. Matrix v1.1 — kernbesluiten

De volledige uitvoerbare matrix staat in:

- `backend/app/testing/authorization_matrix_acceptance.py`

Belangrijke onderscheidingen voor huishoudfuncties:

| Functie | Lid | Beheerder | Superuser | Frontteamlid |
|---|---:|---:|---:|---:|
| Admin | Nee | Ja | Ja | Ja |
| Externe databases | Nee | Nee | Ja | Ja |
| Catalogus bekijken | Ja | Ja | Ja | Ja |
| Catalogus wijzigen | Nee | Nee | Ja | Ja |
| Catalogus beheren | Nee | Nee | Ja | Ja |
| GPC bekijken | Ja | Ja | Ja | Ja |
| GPC wijzigen | Nee | Ja | Ja | Ja |
| GPC beheren | Nee | Ja | Ja | Ja |
| Technisch Platformbeheer | Nee | Nee | Nee* | Nee |

`*` Een Superuser krijgt technisch Platformbeheer alleen wanneer hetzelfde platformaccount daarnaast afzonderlijk de rol `platform.platform_admin` heeft. De role-stacking runtimecutover valt buiten 9.1.8a.

Daarom mag een beheerder op het Catalogusoverzicht wel GPC classificeren, maar geen algemene catalogusgegevens wijzigen of beheren. Een gewone Superuser heeft functionele v2-platformauthority, maar niet automatisch de technische Platformbeheerder-set.

## 5. Automatische regressietest

De matrix wordt volledig gecontroleerd door:

```text
backend/app/testing/authorization_matrix_acceptance.py
```

De test voert **192 controles** uit:

- 45 functionele huishoudrechten × 4 rollen;
- 12 extra structuur- en risicocontroles, inclusief de Superuser-v2/Platformbeheerder-separation.

Een geldige run eindigt met:

```text
GO: alle 192 controles zijn conform household-matrix v1.1 + Superuser-v2
AUTORISATIEMATRIX_ACCEPTATIE_GREEN
```

Een afwijking geeft **NO-GO** en vermeldt:

- domein;
- functie;
- rol;
- verwacht resultaat;
- werkelijk resultaat;
- technische permissiesleutel.

## 6. Lokale uitvoering

Vanuit de repository-root:

```powershell
.\RUN_AUTORISATIEMATRIX_TEST.bat
```

Het startbestand:

1. bouwt de actuele backend-image;
2. vernieuwt de backendcontainer;
3. voert de matrixacceptatietest uit;
4. rapporteert GO of NO-GO.

## 7. CI-regressiegate

GitHub Actions-workflow:

```text
.github/workflows/authorization-matrix-acceptance.yml
```

Deze workflow draait bij iedere relevante pull request en kan handmatig worden gestart. Een matrixafwijking blokkeert het regressie-oordeel.

## 8. Verplichte handmatige UI-steekproef

De automatische test bewijst de rol-permissietoekenning. Daarnaast blijft een UI-steekproef verplicht om te bewijzen dat schermen, knoppen en routes de permissies correct toepassen.

Minimale steekproef:

1. **Lid**
   - Admin niet zichtbaar en `/admin` geweigerd;
   - Externe databases niet zichtbaar en directe route geweigerd;
   - Catalogus bekijken toegestaan;
   - GPC wijzigen geweigerd.
2. **Beheerder**
   - Admin zichtbaar en bereikbaar;
   - Externe databases niet zichtbaar en directe route geweigerd;
   - GPC classificeren toegestaan;
   - algemene catalogusmutaties geweigerd.
3. **Superuser**
   - Admin zichtbaar en bereikbaar voor huishoudbeheer;
   - Externe databases zichtbaar en functioneel bereikbaar;
   - Catalogus en GPC volledig beheerbaar binnen de v2 functionele scope;
   - technische Platformbeheerpagina's/rechten geweigerd tenzij afzonderlijk Platformbeheerder toegekend;
   - `platform.special_roles.manage` niet impliciet toegekend.
4. **Frontteamlid**
   - Externe databases zichtbaar en bereikbaar volgens de Frontteamset;
   - rechten conform de frontteamkolom;
   - geen technische platformrechten tenzij afzonderlijk toegekend.

Controleer per rol:

1. zichtbaarheid van de tegel;
2. openen via normale navigatie;
3. directe URL;
4. zichtbaarheid/disabled-state van mutatieknoppen;
5. daadwerkelijke backendresponse bij een toegestane en verboden actie;
6. correcte 401/403-afhandeling;
7. behoud van de actieve context in de header.

## 9. Wijzigingsbeheer

Een wijziging in autorisatie is pas compleet wanneer alle volgende onderdelen in dezelfde wijziging zijn aangepast:

1. PO-matrix/doelcontract en dit document;
2. `ROLE_PERMISSIONS` en permissieregistratie;
3. sessiepayload en server-side autorisatie;
4. frontendguards en zichtbaarheid;
5. automatische matrixacceptatietest;
6. handmatige UI-steekproef;
7. relevante release- en regressiedocumentatie.

Losse uitzonderingen of hardgecodeerde e-mailcontroles buiten de canonieke Superuser-identiteit zijn niet toegestaan.
