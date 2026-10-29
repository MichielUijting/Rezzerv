# Taxonomie-eerst – proef 7: betere dekking op bestaande Catalogus-GTIN

**Doel:** verbreed *uitsluitend de voorstellen* uit proef 6, met dezelfde
gratis/royaltyvrije Shopify- en CBS-aggregatieniveaus. Geen GS1-productservice,
geen betaald productmatchmodel en geen database-mutatie.

## Scope en bewijs

- Alleen de centrale InHuis-Catalogus, `global_products`, met reeds bestaande
  geldige GTIN (8, 12, 13, 14 cijfers inclusief controlegetal).
- **Niet** de losse ED2-bonartikelen; **niet** nieuwe barcodes verkrijgen,
  artikelcodes afleiden, productgroepen vervangen of huishoudartikelen wijzigen.
- Bestaande PostgreSQL-backend in één `SET TRANSACTION READ ONLY`, direct
  `rollback`. Pas daarna publieke OFF-GETs op **exact dezelfde** GTIN,
  maximaal 100 unieke codes, minstens zes seconden tussen aanvragen.
- Uitsluitend lokale, reeds gepinde Shopify v2026-08 NL + Engelse
  voedsel-/dranknamen (MIT) en CBS ECOICOPv2 2026 (CC BY 4.0).
- OFF levert productinformatie, **geen officiële Shopify-ID**. Een OFF-
  categorie of productnaam is feilbaar. OFF ODbL-voorwaarden voor later
  systematisch productiehergebruik apart beoordelen.

## Beslisvolgorde

1. Herbereken voor elk OFF-gevonden, exact via GTIN geïdentificeerd
   Catalogusartikel de **proef-6-uitkomst** als referentie.
2. **Behoud** een concreet proef-6-voorstel of een meervoudige match;
   een onzekere fallback mag dat niet overschrijven. De waarschuwing voor
   samengestelde producten blijft zichtbaar.
3. Zoek bij tot dusver onbekende artikelen conservatief in Nederlandse
   OFF-categorietags en de reeds door OFF getoonde categorietekst. Gebruik
   expliciete, gedocumenteerde brede vertaalsleutels zoals `rookworst` naar
   de bestaande Shopify-familie Vleeswaren/Worsten; **nooit** een zelf
   bedachte Shopify-code.
4. Bij ontbrekende/ongeschikte OFF-categorie kan een expliciete
   soortnaam in **beide** beschikbare productnamen (OFF en Catalogus)
   een breed Shopify-voorstel opleveren, bijvoorbeeld `rundergehakt` naar
   Vlees. Als slechts één naam het soortartikel bewijst, krijgt het voorstel
   een aparte controlevlag; een aantoonbaar naamconflict verhindert de fallback.
5. Verwar *bereidingsvorm* niet met ingrediënt: aardappelfrites zijn geen
   verse aardappelen; `Cayennepeper` blijft bij conflicterende OFF-labels
   meervoudig, `Bobotie` met kruidenlabels krijgt nooit stil een
   kant-en-klaarmaaltijdtype.
6. Resultaten blijven in een lokaal TXT-rapport, naast de status van proef 6,
   inclusief verschillen, bronregel, waarschuwing en Shopify-hiërarchie.

## Interpretatie

De rapporttelling **"voorstellen" is geen nauwkeurigheidscijfer**. Een
**NAAM_BREED**-voorstel is minder zeker dan een letterlijk OFF-label;
beide vereisen beoordeling vóór eventuele classificatie-opslag. De CBS-code
is een *lokale indicatieve vergelijking*, geen officiële producttoewijzing.
Het onderzoek kan niet vaststellen of de bestaande GTIN destijds handmatig
door een Superuser/frontteamlid is toegekend.

## Oplevering en test

- `tools/inhuis_taxonomy_proof7_core.py`: alleen voorstellen, geen I/O.
- `tools/inhuis_taxonomy_proof7.py`: alleen bestaande read-only catalogus +
  expliciete OFF-GET, geen ED2-query, writes of nieuwe services.
- `tools/inhuis_taxonomy_proof7_selftest.py`: offline regressietest inclusief
  fouten/ambiguïteiten.
- Windows 1-klik `Inhuis_Taxonomie_Proef7_Catalogus_1klik.cmd` (los, niet
  in repo), rapport `Downloads\Inhuis_Taxonomie_Proef7_Catalogus_Resultaat.txt`.
  Start geen Dockercontainer, wijzigt niet de database en sluit niet vanzelf.

De Product Owner deelt het werkelijke TXT-rapport voor beoordeling.
Een eventuele implementatie van de classificaties is een **nieuwe aparte
opdracht**, met audit, back-up, rollback en autorisatiecontrole.

TEST_LEVEL_PROVISIONAL: L

Reden: diagnostische tool met backend-/PostgreSQL-connector, onbekend CI-pad;
fail-closed. Geen wijzigingen in applicatieruntime of schema.

STYLEGUIDE_IMPACT: none

STYLEGUIDE_REASON: geen UI- of componentwijzigingen.
