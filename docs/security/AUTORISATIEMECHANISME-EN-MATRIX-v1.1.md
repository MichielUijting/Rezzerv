# Rezzerv autorisatiemechanisme en autorisatiematrix v1.1

Status: **canonieke functionele en technische basis voor PR #216**

Overgangsstatus: dit document en de uitvoerbare 190-check matrix blijven
tijdelijk de beschrijving en regressiebaseline van de huidige runtime. Het
PO-goedgekeurde functionele doelcontract staat vanaf v2.0 in
`docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md`. Implementatiestap 9.1 moet de
runtime en regressies bewust met dat doelcontract in overeenstemming brengen;
een verschil tussen v1.1 en v2.0 mag tot die tijd niet stilzwijgend worden
opgelost.

## 1. Doel

Deze documentatie legt vast:

- hoe Rezzerv authenticatie en autorisatie uitvoert;
- welke rollen bestaan;
- welke rechten per rol gelden;
- hoe de matrix automatisch en handmatig wordt getest;
- welke regressiegates verplicht groen moeten zijn.

De autorisatiematrix v1.1 is door de Product Owner gecontroleerd en is leidend voor implementatie, tests en toekomstige wijzigingen.

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

Erft de toegestane beheerder- en ledenrechten, krijgt alle platformrechten en heeft toegang tot systeemhuishouden `0`. De canonieke identiteit is `supergebruiker@rezzerv.local`.

De superuser heeft tevens volledige toegang tot **Externe databases**.

### Frontteamlid

Is een afzonderlijke rol met de rechten die in de kolom **Frontteamlid** met **Ja** zijn gemarkeerd. Een frontteamlid heeft volledige toegang tot **Externe databases**.

## 4. Matrix v1.1 — kernbesluiten

De volledige uitvoerbare matrix staat in:

- `backend/app/testing/authorization_matrix_acceptance.py`

Belangrijke onderscheidingen:

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
| Platformbeheer | Nee | Nee | Ja | Nee |

Daarom mag een beheerder op het Catalogusoverzicht wel GPC classificeren, maar geen algemene catalogusgegevens wijzigen of beheren.

## 5. Automatische regressietest

De matrix wordt volledig gecontroleerd door:

```text
backend/app/testing/authorization_matrix_acceptance.py
```

De test voert **190 controles** uit:

- 45 functionele rechten × 4 rollen;
- 10 extra structuur- en risicocontroles.

Een geldige run eindigt met:

```text
GO: alle 190 controles zijn conform matrix v1.1
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

Deze workflow draait bij iedere pull request en kan handmatig worden gestart. Een matrixafwijking blokkeert het regressie-oordeel.

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
   - Admin zichtbaar en bereikbaar;
   - Externe databases zichtbaar en volledig bereikbaar;
   - Catalogus en GPC volledig beheerbaar;
   - platformfuncties toegestaan.
4. **Frontteamlid**
   - Externe databases zichtbaar en volledig bereikbaar;
   - rechten conform de frontteamkolom;
   - geen platformrechten tenzij afzonderlijk toegekend.

## 9. Wijzigingsbeheer

Een wijziging in autorisatie is pas compleet wanneer alle volgende onderdelen in dezelfde wijziging zijn aangepast:

1. PO-matrix en dit document;
2. `ROLE_PERMISSIONS` en permissieregistratie;
3. sessiepayload en server-side autorisatie;
4. frontendguards en zichtbaarheid;
5. automatische matrixacceptatietest;
6. handmatige UI-steekproef;
7. relevante release- en regressiedocumentatie.

Losse uitzonderingen of hardgecodeerde e-mailcontroles buiten de canonieke superuseridentiteit zijn niet toegestaan.
