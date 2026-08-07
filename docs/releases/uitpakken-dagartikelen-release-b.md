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

### PO-acceptatie B1

- Functionele PO-test uitgevoerd op 4 augustus 2026.
- Resultaat: **GO**.
- Bevestigd door PO:
  - beide tabellen en checkboxes werken correct;
  - groepswerking werkt aan/uit naar de gekoppelde artikelen;
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

### Gerealiseerd

- Uitpakken leest per gekoppeld huishoudartikel de actuele artikelstandaard uit B1.
- Bestaande en nieuw aangemaakte huishoudartikelen gebruiken consequent de echte `household_article_id`.
- Een opgeslagen artikelkoppeling blijft na verversen zichtbaar in **Mijn artikel**.
- `DIRECT_CONSUMPTION` zet de bestaande bonregel automatisch op de beschermde bestemming **Direct / Direct**.
- Een wijziging in Beheer Artikelgroepen wordt na opnieuw laden van Uitpakken opnieuw toegepast.
- Normale `STOCK`-artikelen behouden de bestaande locatiekeuze.
- De bestaande voorraadmutatie is in B2 nog niet gewijzigd.

### PO-acceptatie B2

- Functionele PO-test uitgevoerd op 4 augustus 2026.
- Resultaat: **GO**.
- Bevestigd door PO:
  - huishoudartikel **Appel** stond in Beheer Artikelgroepen op `DIRECT_CONSUMPTION`;
  - een bonregel kon aan het bestaande huishoudartikel Appel worden gekoppeld;
  - **Mijn artikel** bleef na verversen op Appel staan;
  - **Locatie** werd automatisch **Direct / Direct**;
  - **Direct / Direct** bleef na verversen behouden;
  - de overige Uitpakken-regels bleven ongewijzigd functioneren.

### Technische eindstatus B2

- Eindcommit: `a29e0ebf`.
- Frontend cookie session authority: groen.
- Authorization matrix acceptance: groen.
- Household viewer role regression: groen.
- Uitpakken dagartikelen Release A: groen.
- B2 is functioneel en technisch afgerond.

### Vastgelegd UX-verbeterpunt

Tijdens de PO-test is vastgesteld dat de huidige locatiekeuze ook een hoofdlocatie zonder sublocatie kan laten kiezen, waarna pas achteraf een validatiemelding verschijnt. Dit blokkeert B2 niet.

Vervolgactie:

- bestaande locatie-/sublocatiekiezer elders in Rezzerv opsporen;
- deze generiek hergebruiken in Uitpakken;
- alleen geldige locatie-/sublocatiecombinaties aanbieden, of eerst een locatie en daarna alleen de bijbehorende sublocaties;
- dubbele locatiekeuzecode verwijderen.

Dit verbeterpunt wordt afzonderlijk opgepakt en niet stilzwijgend in B3 vermengd.

## Deelrelease B3 — Tijdelijke afwijking per bonregel

### Doel

Een huishoudlid kan voor één uitpakregel afwijken van de blijvende artikelstandaard, zonder die artikelstandaard te wijzigen.

### Functioneel contract

- Zonder afwijking gebruikt de regel de artikelstandaard.
- Een dagartikel kan voor één regel tijdelijk worden gewijzigd naar **Opslaan in voorraad**.
- Een normaal artikel kan voor één regel tijdelijk worden gewijzigd naar **Direct consumeren**.
- Een tijdelijke afwijking geldt alleen voor de betreffende bonregel.
- Bij een volgende aankoop wordt opnieuw begonnen met de blijvende artikelstandaard.
- `DIRECT_CONSUMPTION` gebruikt automatisch **Direct / Direct**.
- `STOCK` vereist een geldige normale locatie-/sublocatiekeuze.
- De gebruiker kan de afwijking verwijderen en terugkeren naar de artikelstandaard.

### Eerste technische slice

De centrale frontendlogica voor effectieve verwerking is toegevoegd:

```text
effectieve verwerking = regelafwijking, indien aanwezig
                        anders artikelstandaard
```

Dezelfde functie wordt later hergebruikt door:

- de Uitpakken-UI;
- regelvalidatie;
- de B4-verwerkingsopdracht.

### Acceptatie B3

1. Een regel met standaard `DIRECT_CONSUMPTION` start op **Direct consumeren** en **Direct / Direct**.
2. De gebruiker kiest voor die regel **Opslaan in voorraad**.
3. Alleen die regel vraagt daarna om een normale geldige locatie-/sublocatiecombinatie.
4. De blijvende artikelstandaard blijft `DIRECT_CONSUMPTION`.
5. Na verwijderen van de afwijking keert de regel terug naar **Direct consumeren** en **Direct / Direct**.
6. Een `STOCK`-artikel kan tijdelijk op **Direct consumeren** worden gezet.
7. Na opnieuw openen blijft een opgeslagen regelafwijking voor dezelfde bonregel behouden.
8. Een nieuwe aankoop van hetzelfde artikel begint weer met de artikelstandaard.
9. Een gebruiker zonder `unpacking.process` kan geen regelafwijking wijzigen.
10. Een ander huishouden kan de afwijking niet lezen of wijzigen.

## Vervolg na B3

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

B1 en B2 hebben een expliciete functionele PO-GO. De volledige Release B blijft in ontwikkeling totdat ook B3 en B4 technisch groen en functioneel geaccepteerd zijn.
