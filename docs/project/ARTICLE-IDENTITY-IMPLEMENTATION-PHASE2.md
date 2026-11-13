# Inhuis — Artikelidentificatie fase 2: transitieve synoniemgroepveiligheid

**Ontwerp:** ARTICLE-IDENTITY-FUNCTIONAL-DESIGN-v2.md, besluiten 5, 10B, 16B en 24A.
**TEST_LEVEL_PROVISIONAL: L** — centraal backend-schrijfpunt voor Catalogusrelaties.

Dit is de **eerste, afgebakende implementatiestap** van fase 2.
Een nieuwe directe relatie kan bestaande groepen indirect verbinden. Vóór
opslag wordt de volledige resulterende verbonden groep gecontroleerd:
A–B en B–C mogen geen verboden combinatie A–C introduceren.

- De bestaande GTIN-, winkelartikelcode- en bekende GPC-beperkingen gelden
  ook voor indirect verbonden artikelen.
- Alleen expliciete, in de bestaande kwaliteitsbeoordeling geteste
  tegenstrijdige productkenmerken blokkeren (soort, melkvet, lactose,
  zout, suiker, bereiding, smaak). Ontbrekende eigenschappen zijn
  géén bewijs van overeenkomst.
- Een andere verpakkingsgrootte is niet automatisch verboden maar
  rechtvaardigt geen automatische hoeveelheidsomrekening.
- De bestaande PostgreSQL-transactielock blijft behouden. Een conflict
  blokkeert de gehele nieuwe bulk met 409 en rolt ook tussentijdse
  classificatiekeuzes terug. Bestaande opgeslagen relaties worden niet
  verwijderd of gemuteerd en reeds bevestigde paren blijven idempotent.
- Uitsluitend centrale Catalogusproducten en bevestigde synoniemparen
  worden gelezen; geen huishoud-/voorraad-/kassabonmutaties.

**Nog open binnen fase 2:** geteste productfamilies (15A/23A),
goedgekeurde hoeveelheidsfactoren (13B/17B/25A) en expliciete
groepsgevolgenpreview in de UI. Daarna volgen de apart begrensde
fasen 3 (Voorraad/Bijna op) en 4 (historisch herstel).
Geen automatische repair van oude groepen of gedeelde huishouddata.

Voorlopige testklasse L. Tijdens Draft eerst gerichte tests; pas
op de definitieve kandidaat versiesync, normale/preflight en F7 Full.
Merge en deployment blijven aparte expliciete PO-besluiten.
