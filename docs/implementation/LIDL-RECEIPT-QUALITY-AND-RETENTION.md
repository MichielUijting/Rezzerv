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
