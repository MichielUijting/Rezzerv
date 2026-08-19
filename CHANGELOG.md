# Changelog

## Rezzerv-MVP-v01.12.110 - 2026-08-19
- Bestaande, onaangeraakte Kassa-bonnen met een oude `review_needed` parseruitkomst worden éénmalig veilig opnieuw geparsed uit hun opgeslagen ruwe bron.
- Fail-closed herstelgrens: bonnen met gebruikerscorrecties, validatie, artikel-/productkoppelingen, Uitpakken-batches, voorraad-events of verwijder-/archiefstatus worden niet automatisch gewijzigd.
- Herstel is generiek en bron-/statusgedreven; er zijn geen winkelnamen, bonnamen, hashes of productteksten hard-coded in de migratielogica.
- De éénmalige herstelrun wordt geaudit in de vaste `/app/data` runtime-opslag en draait buiten de requestflow, zodat API-start niet afhankelijk wordt van lange OCR-runs.
- CI borgt dat alleen onaangeraakte `review_needed` bonnen kandidaat zijn en dat de herstelrun éénmalig is.
- Parser-, OCR-, scannerboundary- en Externe-databasesherstel uit v01.12.109 blijven inhoudelijk behouden.

## Rezzerv-MVP-v01.12.109 - 2026-08-19
- Kassa-regressie hersteld: geprijsd statiegeld/emballage, verzend-/bezorgkosten en expliciete prijsverlagingen blijven financiële bonregels en tellen mee in de boncontrole, maar blijven uitgesloten van voorraad.
- Eerste-upload OCR geborgd: backend startup wordt fail-closed wanneer de primaire PaddleOCR-runtime niet gereed is, zodat een koude runtime niet stil naar een zwakkere OCR-uitkomst terugvalt.
- Scannerboundary borgt line-count-equivalentie tussen parser, canonical receipt en teruggenormaliseerde bonregels.
- Historisch bewezen Externe-databasesherstel en generieke sticky-headercorrectie uit v01.12.108 blijven behouden.

## Rezzerv-MVP-v01.12.108 - 2026-08-19
- QA-herstel: resizable kolomkoppen behouden nu generiek hun sticky-positionering wanneer sticky headers actief zijn.
- De gerichte regressie blijft het echte scrollgedrag van kolomkop en filterrij controleren.
- Functionele scope van v01.12.107 blijft ongewijzigd.

## Rezzerv-MVP-v01.12.107 - 2026-08-19
- Externe databases hersteld op de betrouwbare v01.12.104-overzichtsflow.
- Bestaande filters, paginering, selectie/export, dubbelklikdetail en OFF zoektekst / Zelf zoeken behouden.
- Herkenning bevestigen teruggebracht in hetzelfde bonartikeldetail, zonder tweede hoofdtabel.
- Herkenning bevestigen blijft strikt los van Catalogus, Mijn artikel en voorraadmutaties.
- Sticky kolomkop en filterrij geborgd via het generieke tabelpatroon met gemeten headeroffset.
- Lokale Compose-route kan de PO-frontend expliciet op poort 5147 publiceren zonder de CI-default 5174 te wijzigen.

## Rezzerv-MVP-v01.12.75 - 2026-04-20
- release flow geïmplementeerd
- automatische versionering toegevoegd

\n## Rezzerv-MVP-v01.12.76 - 2026-04-20\n- s - s - s - s\n