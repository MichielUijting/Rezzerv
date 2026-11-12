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

## Expliciet nog NIET geleverd

- Handmatig in Identificeren bevestigde barcodes zonder OFF automatisch als
  Catalogusproduct materialiseren (besluiten 1A/3A/14A).
- Opslag/lookup van beperkte retailer-scoped codes en eventuele historisch al
  onjuist globaal gekoppelde nummers (22A); geen datamigratie in deze PR.
- Automatische semantische synoniemen, hoeveelheidsfactoren of historische
  heridentificatie (23A–26A).
- Geen mutatie van bonnen, huishoudartikelen, voorraad, volumes of lokale data.

Dit is de **eerste technische deelstap**, geen claim dat het volledige nieuwe
functionele ontwerp al is geïmplementeerd. De huidige bestaande functies voor
handmatige ED2-barcodeopslag blijven vooralsnog afzonderlijk van de Catalogus;
de vervolgstap moet het door de PO vastgestelde vertrouwen zonder externe OFF
bevestiging realiseren, met de juiste scope en transactiezekerheid.

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
