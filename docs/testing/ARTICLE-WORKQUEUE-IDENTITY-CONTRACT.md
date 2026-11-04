# Inhuis Artikelbeheer — unieke werkvoorraad (#648)

Status: implementatiecontract bij Draft-PR #650; de actuele code en officiële classificatieautoriteiten blijven leidend.

## Canonieke identiteiten

**Identificeren** leest dezelfde platformbrede, alleen-lezen ED2-projectie als het bestaande Artikelbeheer. De werkvoorraad bevat uitsluitend nog niet gekoppelde bronartikelen. De sleutel is exact de bewezen combinatie winkelketen, bonartikelomschrijving en winkelartikelnummer, niet een artikelnaam of GTIN alleen. Een handmatig ingevoerde barcode is zoekbewijs, nooit een bevestigde centrale productkoppeling. Historische bonregels en huishoudartikelen zijn geen afzonderlijke centrale productidentiteit.

**Classificeren** leest uitsluitend `global_products.id` als canonieke identiteit. Het resultaat heeft precies één rij per actief centraal product. Er kunnen onafhankelijk twee open taken bestaan: `<global_product_id>:gpc` voor ontbrekende officiële GS1 GPC, en `<global_product_id>:cbs` voor ontbrekende actieve CBS ECOICOPv2. Hetzelfde product wordt niet vermenigvuldigd door winkelkoppelingen, bonnen, synoniemparen, huishoudens of classificaties.

## Rechten en schrijfautoriteit

- De read-only endpoints `/api/cbs-classifications/workqueue` en `/identification-workqueue` eisen de bestaande platformpermissie en een Superuser- of Frontteamsessie met de juiste context.
- De GS1- en CBS-panelen slaan uitsluitend op via de al bestaande centrale API's. CBS houdt de huidige optimistische versiecontrole, transactie en audittrail; GS1 houdt de bestaande officiële Brickautoriteit. Er is geen extra writer, stille synoniemkoppeling of voorraadmutatie.
- Na een bevestigde toekenning ververst de centrale werkvoorraad zijn status opnieuw vanuit de database. Onbewezen gelijkenis mag nooit worden gebruikt om identiteiten of classificaties te combineren.

## Aantallen en beschikbaarheid

De producttelling is wereldwijd over niet-verwijderde centrale producten, de taaklijst is per antwoordpagina. De frontend telt alleen bewezen unieke taken over alle volledig geladen pagina's. De identificatietelling telt exact unieke, nog niet gekoppelde winkelbronidentiteiten. Geen enkel getal mengt product-ID's, bronartikelen, synoniemparen en classificatietaken. API-fout of onvolledige telling wordt als onbeschikbaar getoond, nooit als 0.

## Regressiebewijs

- Pure servicetests: unieke sleutels, gescheiden officiële systemen, verschillende winkels, dubbele identiteiten fail-closed, geen ongewenste SQL-mutaties.
- Geïsoleerd PostgreSQL-schema: centrale productidentiteiten, soft-delete, GS1/CBS-versies, bevestigde externe relaties, bevestigde synoniemen en rollen; geen bestaande Inhuis-database of -volume nodig.
- Playwright op mobiel en desktop: drie werkgebieden blijven lazy, één GS1/CBS-artikellijst en twee panelen, correcte taakstatussen, officiële bevestiging en verversing; geen ongevraagde mutaties bij openen.
- Daarna volgen de toepasselijke normale checks, versiecontrole en de volledige F7 op de definitieve SHA.

Automatische synchronisatie, uitzonderingsmonitor, retries en achtergrondverwerking blijven exclusief **issue #649**.
