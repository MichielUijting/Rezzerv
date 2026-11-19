# Inhuis — appbrede performance-eindcontrole (19 november 2026)

Status: broncode-audit op `main` na merge PR #702 (versie 1.12.427), met beperkte correctie in deze PR. **Dit is geen live-belastingmeting of definitieve vaststelling van milliseconden.** Alle constateringen hieronder komen uit actuele broncode/uitvoerbare contracten.

## Reikwijdte en bewijs

De afgesproken reeks PR #694–#702 heeft de belangrijkste lijstschermen gefaseerd verbeterd. Deze eindcontrole onderzoekt: eerste paginalading, heropenen, zoeken/filteren/sorteren, paginering en het verschil tussen pagina- en totaaldataset. De PO heeft de functionele performance van Bijna op en Winkelen expliciet goedgekeurd. Voor de overige schermen zijn geen nieuwe live-opentijden of queryplannen gemeten in deze audit.

| Onderdeel | Actuele code-aanpak | Eindcontrole |
|---|---|---|
| Kassa desktop/mobiel | `/api/kassa/receipts-page` met `page_size=10`; verversing van zoek-/vervolgpagina's zonder herinitialisatie | Serverpagina aantoonbaar in code; blijft bewaakt door contract |
| Uitpakken (bonoverzicht) | `/api/unpack-start-batches` met `page_size=10`, filter-/sorteerparameters op de API | Serverpagina aantoonbaar in code |
| Voorraad mobiel | `/api/voorraad/mobile-page` met pagina/zoekparameters | Serverpagina aantoonbaar in code |
| Voorraad desktop | `/api/voorraad/desktop-page` met `page_size=10`; afwijkende globale filters gebruiken bewust volledige dataset om alle records correct te meenemen | Snelle standaardpagina aantoonbaar; uitzonderingspad functioneel nodig |
| Catalogus mobiel/desktop | `/api/catalog` met `limit=10`, `offset`, serverzoek-/sorteerparameters | Serverpagina aantoonbaar in code |
| Artikelbeheer — Identificeren | `articles-preview?limit=10` maakt eerste regels direct bruikbaar; volledige overzicht wordt daarna opgehaald voor correcte globale filtering | Snelle eerste interactie aantoonbaar; volledige dataset volgt voor globale functies |
| Artikelbeheer — Classificeren | `workqueue-page` met `limit=8`, apart globale `workqueue-summary`; alle selectie-ID's alleen op gebruikersactie | Snelle eerste pagina aantoonbaar in code |
| Artikelbeheer — Werkvoorraad | Vraagt alle classificatieworkqueue-pagina's, bonartikeloverzicht en synoniemanalyse voor consistente, globale taaktellers | **Bekende uitzondering**: volledige samenvoeging kan de eerste bruikbare taak vertragen; niet stil vervangen door onvolledige aantallen |
| Artikelbeheer — Overzicht | Voor deze PR twee volledige opvragen bij openen: synoniemanalyse **en** bonartikeloverzicht, terwijl nog geen artikel geselecteerd is | **Aantoonbaar onnodige initiële aanvraag**: deze PR stelt bonartikeloverzicht uit tot selectie en hergebruikt de read-only snapshot bij volgende selecties |
| Artikelbeheer — Matchen/Synoniemen | Bestaande complete relationele projecties voor globale beoordeling; projectie van zichtbare rijen via bestaande paginering | Functionele volledigheid behouden; geen onbewezen versmalling |
| Bijna op | PR #701: gedeelde huishoudgebonden bulkprojecties en detailverbeteringen | Functioneel door PO goedgekeurd, geen nieuwe live-meting |
| Boodschappen/Winkelen | PR #702: SQL-begrensd zoeken en geen onnodige GPC-opvraag bij lege/bronloze lijst; lijst zelf nog client-side gepagineerd | Functioneel door PO goedgekeurd; totale-lijst-GET blijft een **bewuste uitzondering**, geen beweerde serverpaginering |

## Wijziging in deze PR

Het grafische Artikelbeheer-Overzicht hoeft bij openen uitsluitend de zoekcatalogus te lezen. De zware `articles-overview`-GET wordt pas opgevraagd wanneer een concreet Catalogusartikel is gekozen. Een succesvolle read-only snapshot wordt hergebruikt bij wisselen tussen artikelen; Verversen maakt deze ongeldig. Bij selectiewissels blijven op het scherm uitsluitend de relaties voor het laatst gekozen artikel zichtbaar na alle benodigde bewijzen. De server blijft autoriteit voor bestaande rollen en productidentiteiten; er wordt niets geschreven.

Een bestaande Playwright-fixture test dat (1) de zoekinvoer zonder bonartikel-GET beschikbaar is, (2) selectie alle bevestigde matches toont en (3) wisselen geen tweede volledige bonartikel-GET veroorzaakt. Het bestaande appbrede pagineringscontract bewaakt bovendien de negen snelle eerste-paginapaden.

## Openstaande mogelijkheden: geen claim zonder meting

1. **Werkvoorraad:** de volledige classificatie-/bon-/synoniemcombinatie is functioneel noodzakelijk voor de huidige taakvolledigheid. Een latere gerichte wijziging moet een backend-autoriteit voor globale taaktellers plus een direct bruikbare pagina ontwerpen en bewijzen, inclusief 1.000+ producten en huishoudisolatie. Niet in deze slotcorrectie.
2. **Winkelen:** serverpaginering voor grotere actieve lijsten blijft mogelijk, maar selectie over alle pagina's, globaal zoeken/sorteren, export en directe checkbox-updates moeten eerst worden afgedekt; de PO heeft de huidige performance geaccepteerd.
3. **Overzicht na selectie, Matchen en Synoniemen:** volledige overzichten kunnen nog zwaar zijn bij veel data. Alleen een live request-/querymeting kan indexering, scoped serverprojecties of extra paging onderbouwen.
4. **Heropenen/beeldbelasting:** deze broncode-audit bewijst geen browserpaint-, netwerk- of databasepercentielen. Een reproduceerbare meting op echte omvang, verschillende toestellen en koude/warme start is nodig om latere millisecondeclaims te doen.

Geen productie-, Docker-, database-, migratie- of indexwijziging. De normale regressie- en exact-SHA-gates blijven verplicht voor de definitieve PR-kandidaat.
