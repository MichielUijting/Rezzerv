# Rezzerv rollen- en accountmodel v2.0

Status: **PO-goedgekeurde functionele bron van waarheid voor rollen,
accounttypen, huishoudrelatie, systeemhuishouden 0 en toewijzingsregels.**

## 1. Doel en overgangssituatie

Dit document is het functionele doelcontract voor het toekomstige rollen- en
accountmodel van Rezzerv.

De huidige runtime wordt tijdelijk nog beschreven en bewaakt door:

- `docs/security/AUTORISATIEMECHANISME-EN-MATRIX-v1.1.md`;
- `docs/testing/AUTORISATIE-REGRESSIEPROTOCOL-v1.1.md`;
- de uitvoerbare autorisatiematrix met 190 controles.

Deze v1.1-bronnen blijven de regressiebaseline van de huidige runtime totdat
implementatiestap 9.1 is afgerond. V2.0 is vanaf nu het goedgekeurde functionele
doelcontract. Implementatiestap 9.1 moet runtime, permissies, sessie, rollen en
regressietests bewust met v2.0 in overeenstemming brengen. Tot die tijd bestaat
er dus een bedoelde, gedocumenteerde overgangssituatie. Een conflict tussen het
runtimecontract v1.1 en het functionele doelcontract v2.0 mag niet stilzwijgend
worden opgelost.

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
- Het is het gedeelde systeemhuishouden van de bevoegde Superuser(s).
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
| Toekomstige uitnodigingsflow | Moet een link naar Rezzerv plus Apple App Store en Google Play ondersteunen. |
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
- Technische migratie en normalisatie horen bij implementatiestap 9.1.
- Deze documentatietaak voert geen migratie uit.

## 7. Functioneel en technisch onderscheid

| Rol | Context en verantwoordelijkheid |
|---|---|
| Lid | Regulier huishouden |
| Beheerder | Regulier huishouden plus huishoudbeheer |
| Frontteamlid | Eigen regulier huishouden als Beheerder plus beperkte Frontteamfuncties |
| Superuser | Functioneel platformbeheer plus systeemhuishouden 0 |
| Platformbeheerder | Technisch platformbeheer |
| IP-eigenaar | Hoogste bevoegdheid over functioneel en technisch platformbeheer plus systeemhuishouden 0 |

Een technische rol geeft niet automatisch functionele centrale rechten. De
functionele Superuserrol geeft niet automatisch technische beheerrechten.
Systeemhuishouden 0 is een bijzondere systeemcontext en geen regulier
gebruikershuishouden.

## 8. Bestaande en toekomstige functionaliteit

### Bestaand; autorisatie te controleren bij implementatie

Bij implementatiestap 9.1 moet eerst in code en runtime worden vastgesteld welke
onderdelen aantoonbaar aanwezig zijn en vervolgens of hun autorisatie met dit
doelcontract overeenkomt:

- Meldingen en de bestaande statussen daarvan;
- Externe bestanden;
- centrale catalogus en universele artikelen;
- GPC;
- externe databronnen;
- systeemhuishouden 0;
- bestaande autorisatie- en sessiefoundation.

Deze opsomming bevestigt geen volledigheid of productiegereedheid. Zo meldt de
huidige actieve projectdocumentatie dat op haar statusdatum geen actieve
Meldingen-API bestond. De actuele implementatie moet bij stap 9.1 opnieuw worden
geïnventariseerd; er wordt geen niet-aantoonbare functionaliteit verondersteld.

### Nog nieuw te bouwen of later uit te werken

- nieuwe functionele platforminstellingen die nog niet in de code bestaan;
- uitgebreide technische Platformbeheerderomgeving;
- volledig beheer van speciale platformrollen waar dit nog niet aanwezig is;
- IP-eigenaarsbeheer;
- extra beveiligde bevestigingsflow voor kritieke IP-eigenaaracties;
- onboarding volgens het nieuw goedgekeurde model;
- contextuele introducties van artikelgroepen, Uitpakken-automatisering,
  Afboeken voorraad en Bijna op.

## 9. Implementatieopdracht 9.1

Deze documentatietaak wijzigt geen runtime. Een afzonderlijk goedgekeurde
implementatiestap 9.1 moet minimaal:

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
8. de 190-check matrix, overige regressietests en documentatie actualiseren naar
   het geïmplementeerde v2.0-contract;
9. bestaande functies uit sectie 8 inventariseren en hun autorisatie gericht
   controleren.

Tot afronding en acceptatie van stap 9.1 blijven v1.1 en de bestaande 190-check
matrix de verplichte runtime- en regressiebaseline.
