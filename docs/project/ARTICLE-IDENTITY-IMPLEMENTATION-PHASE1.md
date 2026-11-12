# Inhuis — implementatie artikelidentificatie: fase 1, deelstap A

**PO-doelontwerp:** 27 vastgestelde besluiten (12 november 2026).
**TEST_LEVEL_PROVISIONAL: L** — barcode/productidentiteit in backend-runtime.

## Doel

Een bewezen centrale GTIN-identiteit is bruikbaar voor herkenning ook als GPC/CBS
nog ontbreekt (PO-besluit 4A). Een restricted-circulation barcode (o.a. 02 en
20–29 binnen een GTIN-13) wordt niet vanwege een geldige controlesom als
wereldwijd uniek gezien (14A/22A). De bestaande Individuele Lidl-beoordeling
blijft onderdeel van **Artikelbeheer → Identificeren**.

## Nu geleverd

- Een gedeelde, read-only barcode-scopeclassificatie die 12-/13-/14-cijferige
  varianten conservatief onderscheidt en geen winkelinterne nummeropbouw raadt.
- GTIN-validatie meldt voortaan aanvullend de scopehint.
- Bestaande exact-product lookup vereist actieve Catalogusidentiteit en
  bijpassende GTIN-identiteit, **niet** een GPC-classificatie.
- Globale lookup en globale productaanmaak op herkenbare restricted-circulation
  nummers stoppen fail-closed totdat een veilige, handmatig bevestigde en
  retailer-gescopeerde opslagroute is gerealiseerd.
- Gerichte unit-/SQLite-isolatietests voor de nieuwe herkenningsregels.

## Werkelijk geïmplementeerd in deze Draft-PR

- Het handmatig **opslaan** van een barcode in Identificeren is direct de
  bevestiging van de artikelidentiteit. Dezelfde transactie koppelt deze
  zonder OFF of classificatie aan een bestaand actief Catalogusproduct of
  maakt er een nieuw aan. Een extra OFF-bevestiging is niet vereist.
- Restricted-circulation/Lidl-codes zijn **uitsluitend bevestigd voor de
  afzonderlijke combinatie winkelketen, bonomschrijving, bonartikelnummer en
  opgeslagen code**; er ontstaat geen mondiale GTIN-identiteit.
- Een eerder opgeslagen barcode heeft dezelfde bewijswaarde. Bevoegde
  gebruikers selecteren maximaal 50 van die bestaande artikelen in
  **Artikelbeheer → Identificeren** en gebruiken de actie
  **Bewaarde barcodes koppelen**. De selectie krijgt eerst een bestaande
  Inhuis-gevolgen-/bevestigingsoverlay.
- Voor die bulkactie wordt ieder bonartikel opnieuw aan de centrale
  bronidentiteit getoetst. De bewaarde barcode moet al bestaan en exact
  overeenkomen, ook na de transactievergrendeling. Eén tegenstrijdigheid
  draait de **gehele batch** terug; herhalen is idempotent.
- De batch is bewust geen startupmigratie en geen onzichtbare GET-mutatie.
  Hij verandert uitsluitend Catalogusidentiteiten en verwijzingsmetadata;
  nooit bonnen, huishoudartikelen, voorraad of synoniemen.

## Nog niet geleverd in dit deeltraject

- Correctie van een **andere, reeds opgeslagen Lidl-code** met een
  afzonderlijk gevolgenoverzicht, expliciete bevestiging en auditregistratie.
  De PO beoordeelt die codes per artikel in Identificeren; geen automatische
  vervanging van het bestaande bewijs.
- Resolutie van historisch al ten onrechte globaal geclaimde restricted codes.
  Bestaande conflicten stoppen veilig; zij worden niet automatisch gemerged.
- Semantische synoniemen, geverifieerde productfamilies en hoeveelheidsfactoren
  (23A–25A), doorwerking in Voorraad/Bijna op (20A) en historisch herstel
  van verwijzingen/afgeleide projecties met behoud van bronhistorie (26A).
- Geen mutatie van bestaande ontvangst-/huishouden-/voorraadgegevens,
  geen Docker- of volumeactie en geen automatische classificatie.

## Acceptatie

1. AH Courgette, GTIN 8722800072026, actieve Catalogus + bijpassende identiteit:
   `matched` ook wanneer geen officiële GPC of CBS bestaat.
2. Ontbrekende of tegenstrijdige GTIN-identiteit blijft onveilig.
3. Lidl 2008234600001 wordt nooit door alleen de checksum als globaal product
   gekoppeld; bestaande handmatige beoordeling blijft vereist.
4. Geen huishoud-/voorraadmutaties vanuit barcode-validatie en -lookup.
5. Oude geldige, niet-restricted GTIN-lookup blijft compatibel.

**Branchbeheer:** Draft tot de scoped implementatie binnen deze deelstap,
normale/preflightchecks en versie-/risicogates gecontroleerd zijn. F7 exact
op definitieve SHA indien L verplicht. Geen merge/deploy zonder aparte PO-GO.

## PO-correctie — opgeslagen barcode = vastgesteld bewijs

Het bewaren van een barcode in **Identificeren** is reeds voldoende bewijs.
Er komt **geen tweede bevestiging** en er is geen OFF-verificatie vereist.
Na opslaan wordt een Catalogusproduct gezocht of aangemaakt, zonder verplichte
classificatie en zonder bon-/voorraadmutaties. Deze regel vervangt de eerdere
technische aanname dat handmatig bewaarde codes slechts voorlopige aanwijzingen
waren.

Restricted Lidl-codes zijn wel bevestigd voor die specifieke winkel- en
bonartikelidentiteit, maar niet als wereldwijd unieke GTIN. De PO corrigeert
de Lidl-code later zelf per artikel. Een wijziging die een bestaande koppeling
vervangt krijgt een aparte bevoegde gevolgencontrole (besluiten 9A/12B/27B).
Reeds opgeslagen historische rijen blijven betrouwbaar bewijs; hun veilige
bulk-materialisatie volgt als afzonderlijk controleerbaar herstel, niet als
onzichtbare schrijfactie bij een GET of een startup.


## Relevante bindende PO-besluiten (12 november 2026)

- **14A en 22A:** Lidl/winkelinterne codes worden per winkel en specifieke
  bonartikelidentiteit beoordeeld. De PO kan ze via **Identificeren**
  individueel corrigeren; een geldige controlesom maakt geen mondiale GTIN.
- **15A en 23A:** alleen expliciet beproefde productfamilie-/herkenningsregels
  mogen automatische semantische relaties voorstellen.
- **16B en 24A:** transitieve synoniemketens die verboden of tegenstrijdige
  combinaties opleveren moeten vóór opslag geblokkeerd worden.
- **17B en 25A:** hoeveelheids-/eenheidsfactoren zijn beperkt tot goedgekeurde
  en geteste factoren; nooit onbegrensd op naam afleiden.
- **18A en 27B:** centrale correcties vragen verhoogde server-side
  bevoegdheid: platform-Superuser of een actief, expliciet geautoriseerd
  Frontteamlid, met gevolgenoverzicht, bevestiging en registratie.
- **19B en 26A:** historisch herstel corrigeert de relevante verwijzingen en
  herberekent afgeleide resultaten, maar bewaart oorspronkelijke brongegevens.
- **20A:** synoniemrelaties moeten in een latere, afzonderlijk geteste fase
  doorwerken in Voorraad/Bijna op.
- **21A:** niet aantoonbaar geïdentificeerde artikelen blijven zichtbaar
  als **Nog identificeren** en worden niet stil gekoppeld.

Deze implementatienotitie is geen vervanging van de overige goedgekeurde
ontwerpbesluiten 1–13 of van de bestaande canonieke identity-/securitycontracten.
