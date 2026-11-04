# Werkproces Artikel classificeren — werkvoorraad en synchronisatie

Status: eerste, read-only frontteamwerkplek op Draft-PR. Geen automatische datamutaties, backfills, database- of schemawijzigingen.

## Doel en rollen
- Superuser en frontteam zien dezelfde centrale werkvoorraad; bestaande backend-autorisaties voor koppeling, GS1, CBS en synoniemen blijven ongewijzigd.
- Artikelclassificaties behoren bij centrale Catalogusproducten, niet bij één huishouden of één voorraadregel.
- Er worden geen afleidingen gemaakt van alleen artikelnaam, winkel, foto of onbevestigde kandidaat.

## Werkvolgorde
1. **OFF/productidentiteit** — in Artikel classificeren: filter **Niet gekoppeld**, zoek OFF-kandidaat en bevestig handmatig. Bij ontbrekende betrouwbare match: barcode vastleggen of geval markeren voor nader onderzoek; geen geforceerde koppeling.
2. **GS1 GPC** — filter **Classificatie ontbreekt** na OFF-koppeling; vergelijk GS1 Brick met product en bevestig via bestaande autorisatie. Een niet-gekoppeld bonartikel telt niet automatisch ook als GS1-achterstand.
3. **CBS ECOICOPv2** — open **Artikelclassificaties toekennen**, kies de officiële classificatie van centrale Catalogusproducten en bevestig. De CBS-lijst betreft een andere populatie dan de bonartikelrijen van stap 1-2.
4. **Artikel-synoniemen** — beoordeel voorgestelde paren, inclusief afwijkingen in GS1 en CBS. Een matching-score is een voorstel, geen automatische identiteit.
5. **Classificatieovername/synchronisatie** — wordt pas door de afzonderlijke synoniemovernamefunctionaliteit van PR #645 geactiveerd na definitieve goedkeuring en merge. De gekozen classificaties moeten dan in de bestaande GS1- en CBS-autoriteiten landen, met versiebewaking en audit. Tot dan **geen** generieke knop voor blind synchroniseren.
6. **Controle** — vernieuw de werkvoorraad en controleer de betrokken Catalogusartikelen. Gekoppelde relaties en resterende conflicten mogen niet als 'klaar' worden afgevinkt zonder verificatie.

## Eerste monitor (deze PR)
- **OFF niet gekoppeld:** bestaande `articles-overview.counts.unlinked` op bonartikelniveau.
- **GS1 ontbreekt na OFF-koppeling:** bestaande `articles-overview.counts.classification_pending` op bonartikelniveau.
- **CBS ontbreekt:** read-only telling van de bestaande `/api/cbs-classifications/products`-lijst met `classified=false`, op Catalogusproductniveau, met paginering.
- **Synoniemvoorstellen:** bestaande `article-synonyms/analysis.summary.candidate_pairs`; voorstelparen, **geen** aantal bewezen matches en **geen** syncachterstand.
- **Synchronisatieachterstand/mislukkingen:** **niet beschikbaar**: zonder duurzame en geautoriseerde event-/statusprojectie is geen betrouwbare bron. Monitor toont geen kunstmatige nul.
- Iedere bron wordt afzonderlijk beoordeeld. Bij niet-beschikbaar of gewijzigde CBS-paginatotalen verschijnt een onbeschikbare teller en een foutmelding. Geen stilzwijgende nul, geen optelling van ongelijksoortige populaties.
- De monitor is read-only; handmatige verversing. Frontteam mag geen rechten verwerven door de UI.

## Vervolgvoorstel: betrouwbare synchronisatiemonitor
Maak als afzonderlijke backend-PR een uitsluitend leesbare werkvoorraadprojectie over de bestaande bevestigingstransacties en autoriteiten met ten minste `product_id`, `classificatiesysteem`, `status` (wacht / verwerkt / conflict / mislukt / controle nodig), `brongebeurtenis`, `laatste_poging` en `reden`. Definieer expliciet de statusovergangen, de relatie met CBS-historie en GPC-provenance, en idempotente retry onder bestaande locks. Voer geen write-/retryactie uit zonder gericht autorisatie- en auditcontract. Bewijs met PostgreSQL-tests dat tellingen niet dubbeltellen bij meerdere bonregels/synoniemparen, en dat privacy, rollback, concurrente updates en rechten veilig blijven.

## Acceptatie
- Startpagina en paginatitel tonen 'Artikel classificeren' in plaats van 'Externe databases 2'; bestaande URL blijft als compatibele route.
- De monitor gebruikt aantoonbaar de reeds bestaande gegevensbronnen, toont geen onjuiste samengevoegde totaalsom en ververst na een classificatie.
- Verversen en navigeren veroorzaken geen mutaties; CBS en synoniemen met beperkte rechten worden niet als 'nul' voorgesteld.
- Bij GS1/CBS-afwijking blijft expliciete keuze van PR #645 leidend zodra die afzonderlijke PR is gemerged.
- Frontteam en superuser kunnen het werkproces gebruiken zonder toegang tot extra technische bediening; overige rollen houden hun bestaande beperkingen.
- De definitieve kandidaat krijgt een gesynchroniseerde patchversie, normale/preflightchecks en toepasselijke F7-regressie conform repo-policy.
