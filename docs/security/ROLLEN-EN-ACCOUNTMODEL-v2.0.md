# Rezzerv rollen- en accountmodel v2.0

Status: **PO-goedgekeurde functionele bron van waarheid voor rollen,
accounttypen, huishoudrelatie, systeemhuishouden 0 en toewijzingsregels.**

9.1.9 is de executable acceptance closure die de reeds geïmplementeerde v2-runtime
formeel als runtime- en regressiebaseline afsluit. Tot de merge van die closure
blijven de v1.1-bronnen verplicht als compatibility-subgate; na succesvolle
9.1.9-merge zijn dit document en `AUTORISATIE-REGRESSIEPROTOCOL-v2.0.md` de
canonieke rollen-v2 bronnen.

## 1. Doel en acceptatiestatus

Dit document is het functionele contract voor het rollen- en accountmodel van
Rezzerv. De hoofdonderdelen van implementatiestap 9.1 zijn inmiddels in runtime
gebracht: householdrollen, expliciete sessiecontexten, systeemhuishouden 0,
Frontteam, Superuser-v2, Platformbeheerder, IP-owner special-role management,
onboarding en Superuser + Platformbeheerder role stacking.

De historische compatibilitybronnen blijven behouden:

- `docs/security/AUTORISATIEMECHANISME-EN-MATRIX-v1.1.md`;
- `docs/testing/AUTORISATIE-REGRESSIEPROTOCOL-v1.1.md`;
- `backend/app/testing/authorization_matrix_acceptance.py`, met 192 actuele
  household-compatibility/Superuser-v2 controles.

Deze bronnen zijn na 9.1.9 geen zelfstandige volledige platformrollen-bron van
waarheid meer. De volledige v2-acceptatie wordt bewaakt door:

- `docs/testing/AUTORISATIE-REGRESSIEPROTOCOL-v2.0.md`;
- `docs/security/ROLLEN-V2-9.1-ACCEPTANCE-CLOSURE.md`;
- `.github/workflows/roles-v2-acceptance-closure.yml`;
- de bestaande focused role/session/security gates.

Een conflict tussen een historische compatibilityclaim en dit v2-contract mag
niet stilzwijgend ten gunste van v1.1 worden opgelost.

## 2. Rollen en accounttypen

### 2.1 Lid

- Hoort bij een regulier huishouden.
- Wordt normaal uitgenodigd door een Beheerder.
- Gebruikt de functionele huishoudinstellingen die de Beheerder heeft bepaald.
- Beheert die huishoudinstellingen niet zelf.
- Is geen platformrol.

### 2.2 Beheerder

- Hoort bij een regulier huishouden.
- Iemand die Rezzerv normaal zelf registreert, wordt automatisch Beheerder van
  een nieuw regulier huishouden.
- Beheert huishoudinstellingen en leden.
- Kan een Lid uitnodigen.
- Kan een Lid promoveren tot Beheerder.
- Kan een Beheerder terugzetten naar Lid zolang minimaal één Beheerder
  overblijft.
- In ieder regulier huishouden moet altijd minimaal één Beheerder overblijven.
- Is geen platformrol.

### 2.3 Frontteamlid

Frontteamlid is een aanvullende speciale functionele rol.

- Heeft of krijgt altijd een eigen regulier huishouden.
- Is automatisch Beheerder van het eigen huishouden en behoudt daarvoor de
  normale Beheerderfunctionaliteit.
- Heeft daarnaast Frontteamfunctionaliteit.
- Mag via de bestaande Meldingen-functionaliteit:
  - foutmeldingen naar Superuser(s) sturen;
  - ideeën en verbetervoorstellen naar Superuser(s) sturen;
  - meldingen van Superuser(s) ontvangen;
  - peilingen van Superuser(s) ontvangen en beantwoorden.
- Meldingen gebruikt de bestaande statussen en werking; er komt geen tweede
  statussysteem.
- Krijgt toegang tot de bestaande functionaliteit Externe bestanden.
- Mag daar een artikel koppelen aan een bestaand universeel artikel.
- Krijgt daardoor niet automatisch onbeperkt beheer over de centrale catalogus.
- Krijgt vanwege de Frontteamrol geen toegang tot huishoudgegevens van andere
  reguliere huishoudens.

### 2.4 Superuser

Superuser is een speciaal functioneel platformaccount.

- Heeft geen persoonlijk of regulier gebruikershuishouden.
- Heeft wel toegang tot het gemeenschappelijke systeemhuishouden 0.
- Voert functioneel platformbeheer uit.
- Ontvangt en beantwoordt Frontteammeldingen.
- Stuurt meldingen en peilingen naar Frontteamleden.
- Beheert de centrale catalogus en universele artikelen.
- Kan universele artikelen toevoegen of corrigeren en waar nodig gecontroleerd
  koppelingen herstellen.
- Beheert GPC en centrale classificatie functioneel.
- Heeft volledige functionele toegang tot Externe bestanden.
- Beheert externe databronnen functioneel.
- Gebruikt functionele centrale Rezzerv-functies.
- Erft niet automatisch Beheerderrechten op reguliere huishoudens.
- Nieuwe Superusers mogen uitsluitend door de IP-eigenaar worden aangesteld of
  verwijderd. Een gewone Superuser kan dit niet zelfstandig.

### 2.5 Platformbeheerder

Platformbeheerder is een speciaal technisch platformaccount.

- Heeft geen regulier huishouden.
- Heeft niet automatisch toegang tot systeemhuishouden 0.
- Krijgt alleen toegang tot huishouden 0 wanneer hetzelfde account ook een rol
  of bevoegdheid heeft die deze toegang verleent, bijvoorbeeld Superuser.
- Krijgt niet automatisch functionele Superuserrechten.
- Beheert technisch onder andere:
  - technische status en diagnose;
  - logging en foutonderzoek;
  - achtergrondprocessen en herstelacties;
  - technische koppelingen;
  - technische platformconfiguratie;
  - audit- en beheerhistorie.
- Deze technische functies vormen bij livegang een uitbreidbare basisset.
- Krijgt alleen vanwege de technische rol geen toegang tot de inhoud van
  reguliere huishoudens.

### 2.6 IP-eigenaar

IP-eigenaar is de hoogste, beschermde platformbevoegdheid.

- Heeft geen regulier gebruikershuishouden.
- Heeft vanwege de functionele Superuserbevoegdheden wel toegang tot
  systeemhuishouden 0.
- Heeft functioneel de bevoegdheden van Superuser.
- Heeft technisch de bevoegdheden van Platformbeheerder.
- Hoeft in de UI niet als drie gestapelde rollen te worden getoond en wordt
  zichtbaar aangeduid als **IP-eigenaar**.

De IP-eigenaar kan:

- Superusers aanstellen en verwijderen of deactiveren;
- Frontteamleden aanstellen en de Frontteamrol intrekken;
- Platformbeheerders aanstellen en Platformbeheerderrechten intrekken;
- speciale rollen overzien;
- audit- en beheerhistorie inzien;
- functioneel en technisch platformbeheer uitvoeren;
- systeemhuishouden 0 gebruiken voor tests, diagnose en foutanalyse.

Bescherming van de IP-eigenaar:

- Superusers, Platformbeheerders en Frontteamleden kunnen de IP-eigenaar niet
  verwijderen of degraderen.
- Eigenaarschap mag niet via een normale één-klik-rolwijziging verdwijnen.
- Kritieke acties moeten later worden beschermd met een duidelijke waarschuwing
  inclusief gevolgen, herauthenticatie, een bewuste eindbevestiging voor de
  zwaarste acties en auditregistratie.
- Overdracht van IP-eigenaarschap is later een afzonderlijke uitzonderlijke
  procedure en geen normale rolwijziging.

## 3. Systeemhuishouden 0

- Huishouden 0 is geen normaal gebruikershuishouden.
- Het is het gedeelde systeemhuishouden van de bevoegde Superuser(s) en de
  beschermde IP-eigenaar.
- Het wordt voornamelijk gebruikt voor geautomatiseerde en functionele tests,
  het reproduceren en analyseren van fout- en uitzonderingssituaties en de
  diagnose van Rezzerv-processen.
- Het is geen vervanging voor een privéhuishouden.
- Privégebruik door iemand die ook Superuser is, gebeurt met een afzonderlijk
  regulier account.
- Toegang moet voortkomen uit een bevoegde rol of bevoegdheid en niet uit één
  persoonlijk hardgecodeerd e-mailadres.
- Meerdere bevoegde Superusers kunnen hetzelfde systeemhuishouden 0 gebruiken.
- Huishoudisolatie tussen reguliere huishoudens blijft volledig gelden.
- De systeemcontext moet technisch en functioneel herkenbaar blijven.

## 4. Account- en huishoudregels

| Situatie | Regel |
|---|---|
| Normale nieuwe registratie | Maakt een nieuw regulier huishouden; de gebruiker wordt automatisch Beheerder. |
| Uitnodiging vanuit een huishouden | De gebruiker wordt standaard Lid; voor een normale uitnodiging is geen rolkeuze nodig. |
| Uitnodigingsflow | Gebruikt een beveiligde uitnodigingslink; distributie via app-/storekanalen kan later verder worden uitgebreid. |
| Frontteamlid | Heeft of krijgt een eigen regulier huishouden en is daarvan automatisch Beheerder; de Frontteamrol komt daar bovenop. |
| Superuser | Heeft geen regulier huishouden en wel toegang tot gedeeld systeemhuishouden 0. |
| Platformbeheerder | Heeft geen regulier huishouden en geen automatische toegang tot huishouden 0. |
| IP-eigenaar | Heeft geen regulier huishouden en wel toegang tot huishouden 0. |
| Privégebruik platformaccounts | Een Superuser, Platformbeheerder of IP-eigenaar gebruikt voor privégebruik een afzonderlijk regulier account. |
| Rolstapeling | Eén platformaccount mag Superuser én Platformbeheerder zijn. Frontteamlid is door de verplichte reguliere huishoudcontext een andere constructie. De IP-eigenaar hoeft zichzelf deze rollen niet aanvullend toe te kennen. |

## 5. Toewijzingsbevoegdheden

| Actie | Wie mag dit |
|---|---|
| Lid uitnodigen | Beheerder van dat huishouden |
| Lid → Beheerder | Beheerder van dat huishouden, met behoud van minimaal één Beheerder |
| Beheerder → Lid | Beheerder van dat huishouden, niet wanneer daardoor geen Beheerder overblijft |
| Frontteamlid aanstellen | Uitsluitend IP-eigenaar |
| Frontteamrol intrekken | Uitsluitend IP-eigenaar |
| Superuser aanstellen | Uitsluitend IP-eigenaar |
| Superuser verwijderen of intrekken | Uitsluitend IP-eigenaar |
| Platformbeheerder aanstellen | Uitsluitend IP-eigenaar |
| Platformbeheerder verwijderen of intrekken | Uitsluitend IP-eigenaar |
| IP-eigenaar verwijderen of degraderen | Niet via normale rollenadministratie |

## 6. Legacycompatibiliteit

- `household.viewer` / Kijker is legacy.
- `household.advanced_member` / Geavanceerd lid is legacy.
- Bestaande gegevens mogen niet destructief verdwijnen.
- Legacyrollen zijn geen nieuwe gebruikersrollen en worden niet opnieuw voor
  normale toewijzing aangeboden.
- De runtime bewaart deze rollen als compatibility-/migratievorm waar bestaande
  data dat vereist.
- De normale household role mutation boundary accepteert uitsluitend
  `household.member` en `household.admin`.
- 9.1.9 bewaakt deze non-destructieve grens executable; er wordt geen brede
  destructieve dataconversie uitgevoerd.

## 7. Functioneel en technisch onderscheid

| Rol | Context en verantwoordelijkheid |
|---|---|
| Lid | Regulier huishouden |
| Beheerder | Regulier huishouden plus huishoudbeheer |
| Frontteamlid | Eigen regulier huishouden als Beheerder plus beperkte Frontteamfuncties |
| Superuser | Functioneel platformbeheer plus systeemhuishouden 0 |
| Platformbeheerder | Technisch platformbeheer |
| Superuser + Platformbeheerder | Systeemhuishouden 0 plus de exacte union van functionele en technische platformrechten |
| IP-eigenaar | Hoogste bevoegdheid over functioneel en technisch platformbeheer plus systeemhuishouden 0 en protected special-role authority |

Een technische rol geeft niet automatisch functionele centrale rechten. De
functionele Superuserrol geeft niet automatisch technische beheerrechten.
Systeemhuishouden 0 is een bijzondere systeemcontext en geen regulier
gebruikershuishouden. De combinatie Superuser + Platformbeheerder geeft niet de
IP-owner-only permission `platform.special_roles.manage`.

## 8. Bestaande en toekomstige functionaliteit

### Bestaand en in 9.1 gericht gecontroleerd

De 9.1-lijn en 9.1.9 closure hebben de aantoonbaar aanwezige onderdelen uit de
oorspronkelijke inventaris opnieuw tegen het v2-contract gecontroleerd:

- Meldingen/support en de bestaande platform-supportgrenzen;
- Externe bestanden / externe productbronnen;
- centrale catalogus en universele artikelen via de functionele
  `platform.catalog.*`-grenzen;
- GPC functioneel en de afzonderlijke technische GPC-importgrens;
- externe databronnen / `platform.external_sources.*`;
- systeemhuishouden 0;
- bestaande autorisatie- en sessiefoundation;
- Platformbeheerder-capabilities en none-context;
- speciale-rollenbeheer door IP-owner;
- onboarding, uitnodiging en householdcontext;
- Superuser + Platformbeheerder stacking.

Deze opsomming is een autorisatie-/contextacceptatie en geen verklaring dat elk
mogelijk toekomstig productonderdeel volledig is uitgebouwd.

### Later of buiten implementatiestap 9.1

- nieuwe functionele platforminstellingen die nog niet in de code bestaan;
- uitbreiding van de technische Platformbeheerderomgeving met toekomstige
  capabilities;
- overdracht van IP-eigenaarschap als uitzonderlijke procedure;
- extra beveiligde herauthenticatie/eindbevestiging voor toekomstige kritieke
  IP-eigenaaracties;
- verdere productintroducties of uitbreidingen die niet nodig zijn om het
  rollen-/accountmodel v2 te accepteren.

## 9. Implementatieopdracht 9.1 — closurestatus

De oorspronkelijke implementatieopdracht vereiste minimaal:

1. account-, lidmaatschaps- en rolrepresentatie met v2.0 in overeenstemming
   brengen;
2. permissies en server-side autorisatie aanpassen zonder huishoudisolatie te
   verzwakken;
3. sessie en actieve context geschikt maken voor reguliere huishoudens en de
   bijzondere systeemcontext;
4. de e-mailgebonden toegang tot huishouden 0 vervangen door rol- of
   bevoegdheidsgebaseerde toegang;
5. Frontteamlid, Superuser, Platformbeheerder en IP-eigenaar technisch en
   functioneel onderscheiden;
6. onboarding, uitnodiging en beschermde roltoewijzing implementeren;
7. legacyrollen niet-destructief migreren of normaliseren;
8. de household compatibilitymatrix, overige regressietests en documentatie
   actualiseren naar het geïmplementeerde v2.0-contract;
9. bestaande functies uit sectie 8 inventariseren en hun autorisatie gericht
   controleren.

9.1.9 is de formele acceptance closure van deze opdracht. Vóór de merge van de
9.1.9-kandidaat blijven de v1.1 compatibilitymatrix en alle bestaande focused
gates verplicht. Na een succesvolle exact-head 9.1.9-acceptatie en merge geldt:

- dit document als functionele rollen-/accountbron van waarheid;
- `AUTORISATIE-REGRESSIEPROTOCOL-v2.0.md` als canonical rollen-v2
  regressieprotocol;
- `Roles v2 9.1 acceptance closure validation` als umbrella executable gate;
- de v1.1 matrix/protocollen uitsluitend als historische household
  compatibility-subgate.
