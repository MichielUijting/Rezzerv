# Lidl – betrouwbare bronbonverwerking (Draft-plan)

Basis: main `043802a8f579ce50e6488232c3c23a3bf7b12af2`, na PR #572.

## Aanleiding en bewijs
- 75 opgeslagen Lidl-bonnen; 16 nog niet door gebruiker goedgekeurd.
- De 16 originele Lidl-bonnen zijn handmatig vergeleken: geen ontbrekende productregels; bedragen en kortingen zijn overgenomen.
- Statiegeld van 11-03-2024 (€ 0,60) is onterecht als `product` opgeslagen.
- Bonnen 02-01-2024 en 11-01-2024 zijn financieel sluitend, maar de historische technische parserstatus is `review_needed`.
- Bij de 16 bonnen is de originele digitale JSON-bron niet bereikbaar via het opgeslagen `raw_receipts.storage_path`. De bronbestanden mogen niet op vermoeden worden verwijderd of overschreven.

## Doel en afbakening
1. Nieuwe Lidl-bonregels: gestructureerd statiegeld als `deposit` classificeren; wel in het bedrag, niet in voorraad.
2. Consistente status voor *nieuwe* betrouwbare digitaal genormaliseerde Lidl-bonnen, zonder historische bonnen automatisch goed te keuren of te reparsen.
3. Nieuwe bronbestanden persistent en aantoonbaar beschikbaar maken buiten de vervangbare backendcontainer; vóór omschakeling een veilige migratie/risicocontrole voor eventuele bestaande bronbestanden uitvoeren.
4. Gerichte tests voor normale producten, herhaalde productregels, gewichten, kortingen, statiegeld en bronbestandbehoud.

## Veiligheid
- Geen database-, Docker-volume- of historische boncorrectie binnen de PR zonder apart vastgesteld herstelpad.
- Nooit bestaande volumes weggooien, destructieve containerwijzigingen uitvoeren of automatisch bonnen goedkeuren.
- Bronbonretentie hoort bij gewone en digitale bonnen; zorg dat bestaand data- en filesystemgedrag niet wordt gemaskeerd door een nieuwe mount.
- Bevestig na implementatie de vereiste versie-/CI-/preflightgates en F7 op definitieve kandidaat-SHA voordat Ready for review mogelijk is.

## Acceptatie
- Lidl-statiegeld is canoniek `deposit` en blijft in de bonfinanciën meetellen.
- Geen onbedoelde voorraadgebeurtenis voor statiegeld.
- Een financieel sluitende digitale bon met kortingsregel is niet uitsluitend door korting `review_needed`.
- Bij containervervanging blijft een nieuw opgeslagen digitale bronbon leesbaar.
- Bestaande database/bonnen/volumes zijn onveranderd, tenzij een afzonderlijk veilig migratiepad expliciet wordt uitgevoerd.

## Styleguide-impact
STYLEGUIDE_IMPACT: reviewed-no-change
STYLEGUIDE_REASON: Alleen de semantische depositclassificatie in de Lidl-browserbridge verandert; er is geen zichtbaar ontwerp- of interactieverschil.

## Migratiebeperking
De nieuwe persistente opslag geldt voor nieuwe digitale bonnen. Historische bronbestanden die alleen in een containerfilesystem staan mogen vóór containervervanging niet worden overschreven of verborgen. De lokale PO-testroute stopt daarom vooraf wanneer zulke onbeschermde bestanden aanwezig kunnen zijn.

## Structurele emballageclassificatie (aanvulling PR #573)
- Het centrale canonieke contract blijft leidend: `deposit` wordt `line_role=financial` en `inventory_eligible=false`. Uitpakken filtert op dit vastgelegde gegeven, niet op bontekst.
- De gedeelde digitale importnormalizer classificeert herkenbare geprijsde statiegeld-, emballage- en fustregels voor Lidl, AH en Jumbo als `deposit`, ook als de bron alleen het generieke type `product` opgeeft. Expliciete andersoortige financiële typen worden niet overschreven.
- De reguliere (OCR/e-mail/PDF/tekst) scanner verrijkt het resultaat *binnen de bronparser* met het type `deposit` wanneer de al bestaande generieke classificatie een geprijsde depositregel herkent. De Canonical V1-adapter blijft alleen de bronfeiten doorgeven.
- De financiële regel en zijn bedrag blijven aanwezig voor totaalcontrole en herleidbaarheid. Producten met bijvoorbeeld het aaneengesloten woord 'statiegeldvrij' blijven gewone producten.
- De bekende bon van 11-03-2024, bedrag € 18,92, bevat historisch een onjuist opgeslagen statiegeldregel van € 0,60 met `line_role=product` en `inventory_eligible=1`. De read-only diagnose bevestigt dit, maar deze codewijziging herschrijft **geen** goedgekeurde bonnen en verwijdert geen voorraadmutaties. Historisch herstel vereist een apart, fail-closed en voor die actuele runtime geverifieerd herstelpad.
- De gemeten bronbonbehoudtest van de PO bevestigde 75 SHA256-gecontroleerde kopieën in persistente opslag; dat is afzonderlijk bewijs, geen bewijs van historische herclassificatie.
- Testniveau L blijft van toepassing. Alle verplichte gates, inclusief finale F7 op exacte head-SHA, moeten groen vóór Ready.
