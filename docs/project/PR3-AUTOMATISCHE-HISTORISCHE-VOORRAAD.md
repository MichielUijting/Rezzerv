# PR3 — Automatische beginvoorraad uit historische bonnen

TEST_LEVEL_PROVISIONAL: L
Reden: wijziging aan huishoudgebonden historische bonverwerking, matches/synoniemen,
voorraadprojectie, mogelijke eventregistratie en de receipt→inventory-keten.

## PO-besluit 21 november 2026

De PO heeft de handmatige beoordeling/bevestiging in gesloten, niet-gemergede
PR #709 afgewezen. Gebruikers hoeven de geschatte beginvoorraad niet in te
vullen of per artikel goed te keuren. De bestaande huishoudinstelling
**Huishoudautomatisering** en eventuele artikelafwijkingen bepalen het effect
van historische aankopen. De programmatuur past de bestaande
matching- en bevestigde-synoniemregels toe.

## Nieuwe standaard bij eerste huishoudstart

- Nieuwe, nog lege huishoudens krijgen bij het **eenmalig afronden van de
  onboarding** de standaard `consume_all_existing_before_purchase`. Bij een
  volgende bewezen herhaalaankoop wordt de oude voorraad op nul gezet en
  blijft de nieuwe aankoop als voorraad over.
- De bestaande huishoudaanpassing en eventuele artikelafwijkingen blijven
  wijzigbaar; een al expliciet ingestelde keuze wordt nooit vervangen.
- Huishoudens met bestaande kassabonnen, voorraad of voorraad-events worden
  niet achteraf aangepast. De standaard wordt niet bij iedere appstart
  opnieuw weggeschreven.
- De gewone winkel-/bonverwerking gebruikt dezelfde bestaande huishoudmodus;
  de historische replay respecteert daarnaast `consumable` en
  `DIRECT_CONSUMPTION`.

## Gemiddeld herhaalaankoopinterval

- Per afzonderlijke kassabondatum telt de gezamenlijke aankoop van een
  canoniek huishoudartikel en zijn **bevestigde** Catalogussynoniemen als
  één aankoopmoment, ongeacht winkelketen of aantal bonregels die dag.
- **Vanaf één herhaalaankoop** (dus twee verschillende aankoopdagen)
  wordt de herhaalaankooptermijn direct berekend en opgeslagen. Er geldt
  **geen** extra minimumwaarnemingsduur, maximumaankoopinterval of
  recentheidseis. De eerste herhaalaankoop geeft simpelweg het verschil
  tussen de twee aankoopdata in dagen.
- Na een volgende herhaalaankoop wordt het gemiddelde herberekend over
  alle waargenomen tussenpozen:
  (laatste aankoopdag - eerste aankoopdag) / (aantal unieke aankoopdagen - 1).
  Historische kassabonnen worden chronologisch geordend, ongeacht importvolgorde.
  Eenzelfde dag levert geen extra interval op.
- Behoud de vereiste **bewezen match/synoniemidentiteit** en betrouwbare
  aankoopdata: een enkele aankoopdatum of onzekere identiteit kan
  nog geen herhaalaankooptermijn opleveren.
- Bij een bevestigde synoniemcomponent wordt dezelfde termijn bij ieder
  betrokken huishoudartikel opgeslagen, ook als een variant zelf niet
  afzonderlijk werd gekocht. Dit betreft *huishoudspecifieke metadata*,
  geen globale Catalogusmutatie.
- Het tabblad **Analyse → Automatisering** toont de gemiddelde termijn en
  het aantal aankoopdagen op desktop en mobiel. Pas bij minder dan
  twee verschillende betrouwbare aankoopmomenten wordt
  'Nog onvoldoende betrouwbare herhaalaankopen' getoond.
- Bij later ingelezen historische bonnen of gewijzigde bewezen relaties
  wordt het gemiddelde opnieuw berekend. Ook **actuele aankopen** met
  een bestaande bewezen huishoudartikelidentiteit worden na de
  historische peildatum toegevoegd aan hetzelfde aankoopdagoverzicht.
  Dit gebeurt automatisch bij een bonimportsignaal of de periodieke
  herkenningscontrole (herstelcontrole circa elke 15 minuten); meerdere
  actuele aankopen op dezelfde dag tellen als één moment.
- Een enkele historische aankoop plus één nieuwe actuele aankoop is dus
  al voldoende voor de eerste opgeslagen termijn. **Ook zonder historische
  bonnen** geeft de eerste actuele herhaalaankoop (twee verschillende
  aankoopdagen) onmiddellijk een berekenbare termijn, waarna de bestaande
  achtergrondcontrole deze opslaat. De worker verwerkt nieuwe huishoudens
  met een actieve bonverwerkingsgrens ook wanneer er geen oude bonnen zijn.
  Iedere volgende afzonderlijke aankoopdag verfijnt het gemiddelde; de
  opgeslagen bronfingerprint verwerkt ook de actuele aankoopbewijzen.
- Deze doorlopende herberekening is **alleen metadata**: zij verandert
  geen actuele voorraadposities, aankoop-/verbruiksevents,
  handmatige minimale voorraad of huishoudelijke voorspeltermijn.
  Bij gewijzigde/ongeldige matches vervallen uitsluitend de eigen
  afgeleide koopritmegegevens.
- De historische termijn is koopgedrag, geen zekerheid over werkelijk
  verbruik en niet zelfstandig een Bijna-op-signaal.

## Canonieke verwerkingsmodi

Aankopen worden per huishouden, bewezen huishoudartikel/synoniemgroep en
kassabondatum chronologisch geordend. Meerdere aankopen op dezelfde dag zijn
één productdag (ook verschillende winkels/bonnen).

- `none` / geen afboeking: beginvoorraad groeit met de aankopen
  (`nieuw = oud + gekocht`).
- `consume_purchased_quantity`: trek maximaal de nieuw gekochte hoeveelheid
  van de oude voorraad af, voeg daarna de nieuwe hoeveelheid toe
  (`nieuw = max(oud, gekocht)`).
- `consume_all_existing_before_purchase`: de oude voorraad wordt vóór de
  aankoop op nul gezet (`nieuw = gekocht`).

De artikelafwijkingen en de expliciete instelling `consumable` gaan vóór
de huishoudstand, overeenkomstig de bestaande live-aankooproute.
`DIRECT_CONSUMPTION` wordt geen fysieke voorraad.

**Eenheden:** bonhoeveelheden en Catalogus-verpakkingsgroottes mogen alleen
worden opgeteld als de dimensies aantoonbaar overeenkomen. Bij verschillen
tussen verpakkingsmaten moet conversie vóór samenvoegen gevalideerd zijn;
nooit impliciet hele pakken naar liter/kg of omgekeerd afronden.

**Matching:** alleen persistente, geverifieerde product-ID's, actieve
huishoudartikelen en bevestigde Catalogus-synoniemketens. Geen match op alleen
bonnaam, winkelcode of onbetrouwbare barcodetoekenning. Ambigue groepen
worden niet als fysiek voorraadaantal gepubliceerd.

## Historische bonnen en actuele voorraad

- Historisch is een bon uitsluitend bij een bewezen aankoopdatum vóór de
  huishoudgebonden datumgrens; ontbrekende/imputeddatum gaat niet mee.
- Onbevestigde historische bonnen staan niet in de gewone Kassa. Productregels
  met bewezen artikelkoppeling moeten desondanks voor de autonome historische
  berekening kunnen tellen; er mag geen fictieve Kassa-goedkeuring plaatsvinden.
- Niet-fysieke regels en dubbele bonnen tellen nooit.
- Inlezen, opnieuw inlezen en een andere volgorde mogen de berekening niet
  dubbel ophogen; herberekening gebruikt de hele vertrouwde bronset.
- Actuele voorraad en actuele aankoop-/verbruiksevents van een bestaand
  huishouden worden nooit retroactief overschreven. Oudere gebruikersdata
  worden niet automatisch gemigreerd of gebackfilld.
- Nieuwe huishoudens hoeven `Waar Inhuis` niet aan te zetten;
  locatievrije voorraad is de standaard waar veilig.
- Berekeningen worden afzonderlijk controleerbaar gemaakt zodat foutieve
  matching of ontbrekende eenheden zichtbaar zijn, zonder gebruikerstaak.

## Acceptatiecriteria

1. Alle drie de huishoudstanden en `consumable`/artikelafwijkingen.
2. Meerdere bonnen op één datum, uit verschillende winkels, in willekeurige
   importvolgorde; oudere naverwerking; dubbele SHA.
3. Eenduidige directe matches, bewezen Catalogusrelaties en bevestigde
   synoniemen (ook ketens met meer dan twee leden).
4. Gelijke en verschillende verpakkingsmaten, gemengde/incompatibele
   eenheden, afrondingsbehoud en `DIRECT_CONSUMPTION`.
5. Locatievrij huishouden, isolatie van twee huishoudens en permissies.
6. Bestaande voorraad en Bijna op blijven beschermd.
7. Geen fictieve of noodzakelijke per-artikelgebruikerbevestiging.
8. Gerichte unit-/PostgreSQL-tests, daarna normale/preflightchecks;
   F7 Full pas op definitieve kandidaat.

## Besluitgrens

Geen merge of deployment zonder afzonderlijke expliciete PO-GO. PR blijft
Draft tijdens implementatie. Niet automatisch oude, onbetrouwbare bonnen
als actuele voorraad boeken.


## Aanvulling PR #732 — historische ontvangstperiode en regelniveau

TEST_LEVEL_PROVISIONAL: L. De automatische bewezen beginvoorraad gebruikt
1 januari van het jaar vóór de huishoudgebonden datumgrens, tot maar exclusief
de datumgrens zelf. De afzonderlijke indicatieve PR2-analyse behoudt haar
read-only onzekerheidscontract.

Digitale bonnen van AH, Lidl en Jumbo met `partial` of `review_needed`
kunnen aantoonbaar betrouwbare fysieke regels bevatten. De selectie kan deze
regels verwerken zonder de volledige bon goed te keuren. Per regel blijven
betrouwbare datum, fysieke rol/voorraadgeschiktheid, positieve gehele stuks,
bewezen huishoudartikelidentiteit en unieke bronidentiteit noodzakelijk.
Onzekere regels en andere parserstatussen blijven uitgesloten.
De bestaande transactiebescherming op actuele en handmatige voorraad blijft
onverminderd van toepassing. Dit is een Draft-tussenreparatie, geen volledige
acceptatie van alle acht gevraagde herstelpunten.


### Veilige hercontrole van reeds opgeslagen bonnen

Het bestaande winkelkoppelingenscherm biedt **Bestaande bonnen opnieuw
controleren**. Alleen de geautoriseerde huishoudbeheerder met een bestaande
historische datumgrens mag de bestaande interne artikelherkenningsworker wekken.
De worker houdt zijn onderhoudspauze, centrale matching-autoriteit,
per-huishouden transacties, idempotente bronfingerprint en
actuele/handmatige-voorraadguards. Er wordt geen nieuwe winkelimport,
bonherparse, accountkoppeling of database-reset aangevraagd.
Een bevestigde aanvraag is **geen** voltooid herberekeningsbewijs.
