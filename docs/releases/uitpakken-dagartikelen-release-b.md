# Uitpakken dagartikelen — Release B

## Doel

Release B maakt het in Release A gebouwde backendfundament voor dagartikelen functioneel bruikbaar in Rezzerv.

## Begrippen

- `STOCK`: het artikel wordt opgeslagen in de actuele voorraad.
- `DIRECT_CONSUMPTION`: het artikel wordt administratief ontvangen en direct geconsumeerd; de netto actuele voorraad blijft nul.
- Artikelstandaard: de blijvende standaardverwerking van een huishoudartikel.
- Regelafwijking: een keuze voor één kassabon-/uitpakregel die de artikelstandaard niet wijzigt.

## Scope

1. Een beheerder of eigenaar kan per huishoudartikel de artikelstandaard instellen op `STOCK` of `DIRECT_CONSUMPTION`.
2. Bestaande en nieuwe huishoudartikelen houden standaard `STOCK` tenzij een beheerder dit wijzigt.
3. Uitpakken toont per bonregel de effectieve verwerking en start met de artikelstandaard.
4. Een huishoudlid mag per bonregel afwijken van de artikelstandaard.
5. Een regelafwijking wijzigt de artikelstandaard niet.
6. `DIRECT_CONSUMPTION` gebruikt automatisch de beschermde huishoudlocatie `Direct / Direct`.
7. `DIRECT_CONSUMPTION` registreert ontvangst en directe consumptie atomair en houdt de netto actuele voorraad op nul.
8. Een afwijking naar `STOCK` verwerkt de betreffende regel naar een normale gekozen voorraadlocatie.
9. Idempotentie, huishoudisolatie en bestaande kassabon-/voorraadketens blijven intact.

## Buiten scope

- Automatische productclassificatie als dagartikel.
- Wijzigingen aan Voorraad of Bijna op buiten wat noodzakelijk is om de juiste voorraaduitkomst te behouden.
- Een permanente standaardwijziging door een gewoon huishoudlid.
- Historische herberekening van eerder verwerkte kassabonnen.

## Autorisatie

- Permanente artikelstandaard wijzigen: bestaand recht `articles.manage`.
- Uitpakregel verwerken en per regel afwijken: bestaand recht `unpacking.process`.
- Huishoudgrenzen worden uitsluitend bepaald door de server-side sessie.

## Deelrelease B1 — Artikelstandaard beheren

### Gerealiseerd

- Beheer vindt plaats via **Instellingen → Artikelgroepen → Beheer Artikelgroepen**.
- De lijst gebruikt `household_articles` en is daardoor onafhankelijk van een actuele voorraadpositie.
- Zowel de tabel **Artikelgroepen** als **Huishoudartikelen** gebruikt één native Rezzerv-`Table`-component.
- Beide tabellen bevatten de kolom **Standaardverwerking**.
- Aangevinkt betekent `DIRECT_CONSUMPTION`; niet aangevinkt betekent `STOCK`.
- Een groepscheckbox werkt één richting door naar alle gekoppelde huishoudartikelen.
- Een individuele artikelwijziging wijzigt geen groepscheckbox en geen andere artikelen.
- Wijzigingen worden direct opgeslagen zonder bevestigingsmelding; alleen fouten worden gemeld.
- Alleen beheerder/eigenaar of `articles.manage` kan de blijvende standaard wijzigen.
- Portals, `MutationObserver` en achteraf geïnjecteerde tabelkolommen zijn expliciet uitgesloten.

### PO-acceptatie

- Functionele PO-test uitgevoerd op 4 augustus 2026.
- Resultaat: **GO**.
- Bevestigd door PO:
  - beide tabellen en checkboxes werken correct;
  - groepswerking werkt in beide richtingen aan/uit naar de gekoppelde artikelen;
  - individuele artikelmutaties blijven geïsoleerd;
  - wijzigingen worden direct geaccepteerd zonder bevestigingsdialoog;
  - tabelopbouw en kolombreedtes zijn bruikbaar zonder horizontale scroll bij normale schermbreedte.

### Technische eindstatus B1

- Eindcommit: `6e5aa494`.
- Frontend cookie session authority: groen.
- Authorization matrix acceptance: groen.
- Uitpakken dagartikelen Release A: groen.
- B1 is functioneel en technisch afgerond.

## Deelrelease B2 — Artikelstandaard tonen in Uitpakken

### Doel

Uitpakken leest per gekoppeld huishoudartikel de actuele artikelstandaard uit B1 en toont deze bij de bonregel.

### Scope B2

- `STOCK` wordt getoond als **Opslaan in voorraad**.
- `DIRECT_CONSUMPTION` wordt getoond als **Direct consumeren**.
- Voor `DIRECT_CONSUMPTION` worden **Locatie: Direct** en **Sublocatie: Direct** als voorgestelde bestemming getoond.
- De gebruiker kan de verwerking in B2 nog niet per regel wijzigen.
- De daadwerkelijke ontvangst- en voorraadmutatie blijft in B2 ongewijzigd.

### Acceptatie B2

1. Een huishoudartikel met standaard `DIRECT_CONSUMPTION` wordt in Uitpakken als **Direct consumeren** getoond.
2. Locatie en Sublocatie tonen voor die regel **Direct / Direct**.
3. Een huishoudartikel met standaard `STOCK` blijft **Opslaan in voorraad** tonen.
4. Een wijziging in B1 wordt na opnieuw openen of verversen in Uitpakken zichtbaar.
5. Bestaande Uitpakken-functionaliteit blijft verder ongewijzigd.
6. Een gebruiker uit een ander huishouden kan de artikelstandaard niet uitlezen.

## Vervolg na B2

- B3: tijdelijke afwijking per bonregel zonder wijziging van de artikelstandaard.
- B4: atomaire verwerking van ontvangst en directe consumptie met netto voorraad nul.

## Functionele acceptatie volledige Release B

1. Beheerder zet een huishoudartikel op `DIRECT_CONSUMPTION`; de instelling blijft bewaard.
2. Een gewoon lid kan de permanente artikelstandaard niet wijzigen.
3. Uitpakken start voor dat artikel met `DIRECT_CONSUMPTION`.
4. Zonder afwijking wordt `Direct / Direct` gebruikt en blijft de netto actuele voorraad nul.
5. Een lid kan voor één regel kiezen voor `STOCK` en een normale locatie selecteren.
6. Alleen die verwerking verhoogt de actuele voorraad.
7. Bij een volgende aankoop staat dezelfde artikelstandaard opnieuw op `DIRECT_CONSUMPTION`.
8. Een normaal artikel met standaard `STOCK` blijft via de bestaande voorraadflow werken.
9. Dezelfde regel opnieuw verwerken veroorzaakt geen dubbele ontvangst, consumptie of voorraadmutatie.
10. Een gebruiker uit een ander huishouden kan de standaard, uitpakregel en Direct-locatie niet gebruiken.

## Technische validatie

- Gerichte backendtests voor standaard, autorisatie, regelafwijking, atomaire verwerking, netto nul, idempotentie en huishoudisolatie.
- Gerichte frontendtests voor weergave, standaardkeuze, afwijking en validatie van locatievelden.
- Bestaande centrale regressie-, sessie-, autorisatie-, kassabon- en voorraadketentests blijven groen.

## Releasebesluit

B1 heeft een expliciete functionele PO-GO. De volledige Release B blijft in ontwikkeling totdat ook B2, B3 en B4 technisch groen en functioneel geaccepteerd zijn.
