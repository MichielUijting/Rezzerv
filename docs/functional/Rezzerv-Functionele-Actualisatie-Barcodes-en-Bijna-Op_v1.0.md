# Rezzerv – Functionele actualisatie barcodes en Bijna op

**Versie:** 1.0  
**Datum:** 27 juli 2026  
**Status:** vastgesteld en deels gerealiseerd  
**Branch:** `feature/external-databases-barcode-input`

## 1. Doel van deze actualisatie

Deze actualisatie vervangt de eerdere omschrijving waarin invoer van een GTIN/barcode nog als toekomstige functionaliteit werd beschreven en waarin **Bijna op** uitsluitend aan een huishoudartikel was gekoppeld.

De actuele functionele lijn is:

1. een barcode kan op meerdere relevante plaatsen in de applicatie worden ingevoerd of gescand;
2. een geldige barcode wordt gebruikt als universele productidentiteit en niet als losse winkel- of zoekcode;
3. een barcodekoppeling mag niet stilzwijgend een huishoudartikel, Producttype of voorraadmutatie overschrijven;
4. **Bijna op** wordt functioneel gebaseerd op `huishouden + Producttype` in plaats van op één huishoudartikel;
5. bestaande huishoudspecifieke instellingen blijven inhoudelijk behouden, maar krijgen het Producttype als nieuw behoefte- en aggregatieanker.

---

## 2. Begrippen en functionele scheiding

| Begrip | Functionele betekenis |
|---|---|
| Bonartikel | Een artikelregel afkomstig uit een kassabon- of aankoopcontext. |
| Huishoudartikel | De huishoudspecifieke representatie van een artikel, met eigen naam, notities en andere gebruikerskeuzes. |
| Globaal product | De centrale, merk- en productgebonden catalogusidentiteit. |
| Barcode / GTIN / EAN | Een universele productcode die een globaal product kan identificeren. |
| Producttype | De officiële functionele productclassificatie waarop voorraadbehoefte en Bijna-op-aggregatie worden gebaseerd. |
| Artikelgroep | De gebruikersordening binnen Rezzerv; geen vervanging voor Producttype of productidentiteit. |

Belangrijkste domeinregel:

> Een barcode identificeert een concreet product. Een Producttype bundelt concrete producten met dezelfde huishoudelijke behoefte. Een huishoudartikel bewaart huishoudspecifieke keuzes.

---

## 3. Barcode-invoer op meerdere plaatsen

### 3.1 Artikeldetail

In Artikeldetail kan de gebruiker een barcode handmatig invoeren of, op een geschikt apparaat, met de camera scannen.

Functioneel gedrag:

- de invoer wordt genormaliseerd en gevalideerd;
- alleen geldige universele codes worden als GTIN/EAN behandeld;
- de barcode kan worden gekoppeld aan het centrale productrecord;
- bij een bestaande andere koppeling is expliciete bevestiging nodig voordat wordt overschreven;
- na opslaan wordt de productverrijking opnieuw opgehaald of gestart;
- de huishoudspecifieke artikelnaam blijft behouden;
- een barcodewijziging is geen voorraadmutatie.

### 3.2 Externe databases – overzicht bonartikelen

In **Externe databases** kan per bonartikel een barcode worden ingevoerd of gescand.

Functioneel gedrag:

- de gebruiker werkt vanuit de concrete bonartikelregel;
- de barcode wordt eerst gevalideerd en opgezocht;
- bij een geldige universele match kan een centrale productkoppeling worden gemaakt;
- winkelcodes, retailer-indexcodes, seedcodes en andere niet-universele codes blijven uitsluitend zoekhulp;
- een kandidaat zonder universele GTIN/EAN mag niet als definitieve productkoppeling worden gepresenteerd;
- zodra een geldige GTIN/EAN bekend is, vervalt de noodzaak om zwakkere kandidaten als hoofdkeuze te tonen;
- de gebruiker ziet de status van de koppeling en het gekoppelde Producttype wanneer dat beschikbaar is.

### 3.3 Camera en handmatige invoer

De scanner en het handmatige veld vormen één workflow:

1. invoer of scan;
2. normalisatie;
3. formaatcontrole;
4. productlookup;
5. beoordeling van de uitkomst;
6. expliciete opslag of koppeling;
7. zichtbare feedback aan de gebruiker.

De toepassing mag niet afhankelijk zijn van uitsluitend cameragebruik. Handmatige invoer blijft altijd beschikbaar.

### 3.4 Geldige universele codes

De huidige functionele acceptatie betreft GTIN/EAN-formaten met 8, 12, 13 of 14 cijfers.

Niet-universele waarden mogen niet als GTIN/EAN worden behandeld, waaronder:

- interne winkelcodes;
- retailer-indexcodes;
- leverancierscodes zonder universele betekenis;
- technische fallback- of seedcodes;
- lege of onjuist gevormde waarden.

### 3.5 Mutatie- en veiligheidsregels

Barcodefuncties moeten aan de volgende regels voldoen:

- een GET-route wijzigt geen gegevens;
- een preview wijzigt geen catalogus, Producttype of voorraad;
- een barcodekoppeling maakt niet automatisch een voorraadregel aan;
- een barcodekoppeling maakt niet automatisch een Producttypebeslissing wanneer die niet expliciet onderdeel is van de bevestigde transactie;
- bestaande centrale koppelingen worden niet stilzwijgend overschreven;
- fouten en lage zekerheid zijn zichtbaar en controleerbaar;
- alle gekoppelde resultaten blijven herleidbaar naar bron en gebruikershandeling.

---

## 4. Bijna op op basis van Producttype

### 4.1 Vastgesteld functioneel besluit

> Een Producttype is Bijna op wanneer de totale, naar basiseenheid omgerekende voorraad van alle eraan gekoppelde artikelen binnen het huishouden de ingestelde Producttypegrens bereikt, of wanneer de voorspelde uitputting volgens het gekozen huishoudbeleid binnen de ingestelde termijn valt.

Bijna op signaleert daarmee een huishoudelijke behoefte en niet het opraken van één merk-, winkel- of bonartikel.

### 4.2 Aggregatie

Alle actieve voorraadregels binnen hetzelfde bevestigde Producttype worden bij elkaar opgeteld, ongeacht:

- merk;
- winkel;
- barcode;
- verpakkingsgrootte;
- voorraadlocatie;
- het onderliggende huishoudartikel.

Voorwaarde is dat de hoeveelheid naar de basiseenheid van het Producttype kan worden omgerekend.

Voorbeelden:

- 2 × 500 ml melk + 1 × 1 liter melk = 2.000 ml binnen hetzelfde Producttype;
- meerdere merken toiletpapier worden gezamenlijk geteld wanneer de Producttype-eenheid en conversie eenduidig zijn.

### 4.3 Onvolledige gegevens

Een voorraadregel wordt niet stilzwijgend verkeerd meegerekend.

Mogelijke situaties:

- Producttype ontbreekt;
- productidentiteit ontbreekt;
- verpakkingsinhoud ontbreekt;
- bron- en doeleenheid zijn niet compatibel;
- meerdere tegenstrijdige koppelingen bestaan.

Deze situaties moeten zichtbaar als ontbrekend, geblokkeerd of te beoordelen worden teruggegeven.

---

## 5. Huishoudspecifieke instellingen op Producttypeniveau

De bestaande instellingen voor huishoudartikelen zijn functioneel hergebruikt voor `huishouden + Producttype`.

| Instelling | Betekenis op Producttypeniveau |
|---|---|
| Minimumvoorraad | Grens waarop het Producttype Bijna op wordt. |
| Streefvoorraad | Voorraadniveau waarnaar moet worden aangevuld. |
| Voorkeurswinkel | Voorkeurswinkel voor de behoefte aan dit Producttype. |
| Prijsindicatie | Indicatieve prijs van de gebruikelijke voorkeurseenheid of -verpakking. |
| Status | Actief of niet actief binnen het huishouden. |
| Standaardruimte | Voorkeursruimte voor producten van dit Producttype. |
| Standaardsublocatie | Voorkeursublocatie binnen de gekozen ruimte. |
| Automatisch aanvullen | Toestaan dat Rezzerv een inkoopvoorstel voor dit Producttype maakt. |
| Verpakkingseenheid | Huishoudelijke voorkeursverpakking, bijvoorbeeld pak of fles. |
| Verpakkingshoeveelheid | Hoeveelheid per voorkeursverpakking in relatie tot de basiseenheid. |
| Notities | Huishoudspecifieke instructies of voorkeuren voor dit Producttype. |

Artikel- en productspecifieke gegevens blijven buiten dit contract, waaronder:

- eigen huishoudartikelnaam;
- barcode;
- merk;
- extern artikelnummer;
- productspecifieke voedingsinformatie;
- actuele locatie van een concrete voorraadpartij.

---

## 6. Berekening van Te kopen

De behoefte wordt eerst in de basiseenheid van het Producttype berekend:

`te kopen = streefvoorraad - actuele Producttypevoorraad`

Wanneer een voorkeursverpakking is ingesteld, mag de uitkomst naar hele verpakkingen worden afgerond.

Voorbeeld:

- Producttypevoorraad: 1.500 ml;
- streefvoorraad: 6.000 ml;
- tekort: 4.500 ml;
- voorkeursverpakking: pak van 1.000 ml;
- voorstel: 5 pakken.

De keuze voor een concreet merk of artikel vindt pas plaats in de inkoop- of winkelcontext.

---

## 7. Voorspelde uitputting

De bestaande huishoudbrede instellingen blijven behouden:

- voorspelling aan/uit;
- aantal dagen vooruitkijken;
- beleidsmodus Aanvullend;
- beleidsmodus Leidend;
- beleidsmodus Leidend met veilige terugval.

De berekeningsscope verandert van huishoudartikel naar Producttype. Daardoor worden aankopen en verbruik van verschillende merken en verpakkingen binnen hetzelfde Producttype als één historie beschouwd.

---

## 8. Migratie van bestaande huishoudartikelinstellingen

De migratieanalyse is read-only en groepeert bestaande huishoudartikelinstellingen per bevestigd Producttype.

Per veld wordt bepaald:

- `ready`: één eenduidige waarde is beschikbaar;
- `missing`: geen waarde beschikbaar;
- `conflict`: meerdere verschillende waarden beschikbaar;
- `review_required`: de waarde is mogelijk overdraagbaar, maar hoeveelheid of verpakking vereist beoordeling.

De analyse:

- schrijft geen Producttype-instellingen;
- wijzigt geen huishoudartikelen;
- wijzigt geen voorraad;
- toont artikelen zonder bruikbare Producttypekoppeling afzonderlijk;
- retourneert ieder huishoudartikel maximaal één keer.

Bestaande artikelinstellingen blijven behouden totdat een gecontroleerde migratie en de definitieve omschakeling zijn geaccepteerd.

---

## 9. Huidige realisatiestatus

### Gerealiseerd

- barcode-invoer en camerascan in Artikeldetail;
- barcode-invoer en camerascan bij bonartikelen in Externe databases;
- validatie van universele GTIN/EAN-formaten;
- lookup- en koppelworkflow voor bonartikelen;
- zichtbare scheiding tussen universele codes en retailer-/zoekcodes;
- serverpaginering van bonartikelen;
- read-only GET voor bonartikelen;
- Producttype-instellingencontract voor minimum en streef;
- uitgebreide huishoudspecifieke Producttype-instellingen;
- read-only Producttype-Bijna-op-preview;
- aggregatie van meerdere artikelen per Producttype;
- eenheidsconversie;
- read-only migratieanalyse;
- deduplicatie van huishoudartikelen in de migratieanalyse.

### Nog niet gerealiseerd

- gebruikersinterface voor Producttype-instellingen;
- gecontroleerde bevestiging en uitvoering van migratievoorstellen;
- volledige Producttypekoppeling van de huidige huishoudartikelen;
- definitieve omschakeling van het zichtbare scherm Bijna op;
- Producttype-gebaseerde voorspelling in productiegebruik;
- koppeling van één Producttypebehoefte naar de inkooplijst.

---

## 10. Functionele acceptatiecriteria

### Barcode

1. De gebruiker kan een barcode handmatig invoeren en met de camera scannen.
2. Alleen een geldige universele code wordt als GTIN/EAN behandeld.
3. Een retailer- of zoekcode wordt niet als universele productidentiteit opgeslagen.
4. Een barcodekoppeling wijzigt geen voorraad.
5. Een bestaande koppeling wordt niet zonder expliciete bevestiging overschreven.
6. De gebruiker krijgt zichtbare fout-, lookup- en succesfeedback.
7. Dezelfde barcodeworkflow levert op verschillende invoerplaatsen dezelfde validatie-uitkomst.

### Bijna op

1. Meerdere merken binnen hetzelfde Producttype leveren één behoefte op.
2. Voorraad over meerdere locaties wordt gezamenlijk geteld.
3. Hoeveelheden worden correct naar de Producttype-basiseenheid omgerekend.
4. Ontbrekende koppelingen en conversies worden zichtbaar gemeld.
5. Minimum en streef zijn huishoudspecifiek per Producttype.
6. Oude huishoudartikelgrenzen beïnvloeden de nieuwe Producttypeberekening niet.
7. De migratieanalyse is read-only en bevat geen dubbele huishoudartikelen.
8. GET-routes veroorzaken geen mutaties.
9. De definitieve omschakeling vindt pas plaats na functionele acceptatie van instellingen en migratie.
