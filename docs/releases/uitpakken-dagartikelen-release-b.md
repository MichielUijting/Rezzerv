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

## Functionele acceptatie

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

Release B is pas gereed voor review wanneer alle technische controles groen zijn. Merge naar `main` vereist daarna een expliciete functionele PO-GO op bovenstaande acceptatiepunten.
