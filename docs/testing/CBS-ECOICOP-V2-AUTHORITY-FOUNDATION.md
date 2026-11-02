# CBS ECOICOPv2 – PR #642, veilig classificatiefundament

## Scope en garanties

Dit is een toevoegende migratie, een strikte CBS-referentievalidator en een gecontroleerde API voor expliciete classificatie. De onafhankelijke CBS-classificatie verandert **geen** GS1-, Shopify-, artikel-, GTIN-, synonym-, huishoud-, bon- of voorraadgegevens.

- De migratie `20261102_01` op `20261031_02` maakt drie nieuwe, aanvankelijk **lege** tabellen.
- De referentietabel vereist zes ASCII-cijfers als tekst, een expliciete oudercode, niveau, naam, bronversie en SHA-256. De databasecontrole werkt zowel met PostgreSQL als met de bestaande SQLite-migratieproeven.
- De producttabel bewaart de expliciete classificatie onafhankelijk van GTIN, met versie en een `is_active`-status.
- De historie bewaart bevestigingen en deactiveringen inclusief actor, tijd en bron.
- Er zijn **geen** automatische referentie-import, Shopify→CBS-omzetting, GS1→CBS-omzetting, barcodeclassificatie of automatische productgelijkwaardigheid.

## Beschikbare serverroutes

De centrale `app.api.router` registreert `/api/cbs-classifications`. Deze routes gebruiken uitsluitend de bestaande sessiecookie- en platformautorisatie:

- `GET /categories?query=...`: uitsluitend de **reeds geverifieerde en geladen** CBS-categorieën, geen fictieve zoekresultaten.
- `POST /bulk-confirm`: atomische bevestiging van maximaal 100 producten, uitsluitend Superuser/Frontteam met bevoegdheid `platform.external_products.link_existing`. Vereist de expliciete CBS-code, bronversie, huidige productnaam en verwachte classificatieversie. Ontbrekende categorie of conflicterende productversie blokkeert de volledige batch.
- `POST /bulk-remove`: atomische deactivering met hogere versie en audit; geen fysieke classificatiehistorie verwijderen.

De classificatie mag ontbreken; bestaande product- en voorraadverwerking wordt niet geblokkeerd. Tweemaal dezelfde CBS-code is **geen** bewijs dat producten fysiek equivalent zijn.

## Officiële bron – nog een verplichte blokkade

Officiële bron: CBS, *De ECOICOPv2 indeling* (12 februari 2026):
https://www.cbs.nl/nl-nl/longread/diversen/2026/de-ecoicopv2-indeling/bijlage

De vastgepinde oorspronkelijke Excelbijlage volgens `tools/taxonomy_proof5_references/NOTICE.md` heeft SHA-256
`6871458274be87aa0126eab1bf334365502438f5e976845df8e5c28cdf95858f`.

De bestaande afgeleide proefreferentie `cbs_ecoicop_v2_2026.json` geeft **440 codes en namen**, maar geen onafhankelijk gecontroleerde volledige ouder-/niveau-hiërarchie. Een controleerbare kopie van de officiële Excelbijlage is in deze werkstap **niet beschikbaar**; daarom worden er **nul** categorieën als operationele authority gepubliceerd. De classificatie-API stopt veilig bij een niet-geladen categorie. Niet de 440 codes stilzwijgend activeren.

Voor het compleet maken van de CBS-implementatie moeten de volledige officiële Excelstructuur, afwijkende/exclusieve regels, geldigheid en hiërarchie worden gevalideerd, waarna een gecontroleerde, reproduceerbare data-import en de gebruikersinterface volgen.

## Gerichte tests en latere fasen

`backend/tests/test_cbs_classification_authority.py` test codes, expliciete hiërarchie en geen productequivalentie.
`backend/tests/test_cbs_classification_service.py` test bevestiging, idempotentie, rollback, audit, verwijdering en classificatie van artikelen zonder GTIN in een geïsoleerde testdatabase.

PR #639 blijft Draft. Zijn GS1 Brick-voorwaarden vervallen pas **na** de nieuwe fysieke productequivalentie- en Bijna-op-implementatie. Fysieke verwijdering van Shopify-/GS1-tabellen volgt uitsluitend na aparte inventarisatie, back-up, herstelproef en specifieke PO-GO.

## Gecontroleerde volledige CBS-categorieauthority (2 november 2026)

De originele CBS-Excelbron is via de geslaagde GitHub-bronimport verkregen en objectief onderzocht: originele SHA-256 `6871458274be87aa0126eab1bf334365502438f5e976845df8e5c28cdf95858f`, classificatietabblad met exact 440 unieke codes, de officiële omschrijvingen en kolom F `Laagste ECOICOPv2 groep (J/N)`. Er zijn 15 afdelingen, 59 groepen, 134 klassen, 224 subklassen en 8 microklassen, met 314 laagste categorieën. Alle 126 niet-laagste codes hebben ten minste één kind; geen enkele oudercode ontbreekt. De afgeleide ouderhiërarchie is voor alle 440 Excelrijen met deze officiële laagste-groep-gegevens, de oorspronkelijke volgorde en niveaustructuur geconfronteerd, niet ongecontroleerd uit cijfers aangenomen.

Gebundelde, versiegepinnde referentie: `backend/app/data/cbs_ecoicop_v2_2026_reference.json`. `tools/inhuis_cbs_reference_contract.py` vergelijkt tijdens GitHub CI iedere officiële code, Nederlandse naam, exacte bronrij, laagste-groep-markering en hiërarchie met de volledige originele Excel-export. Elke afwijking blokkeert de import.

De toevoegende Alembic-revision `20261102_01` vult de nieuwe `cbs_ecoicop_categories` met alle 440 officiële categorieën, **voordat** de write-barrier-triggers worden aangebracht. Deze migratie voert **geen enkele** CBS-toekenning aan producten uit; `global_product_cbs_classifications` en `global_product_cbs_history` blijven leeg. Andere actieve Shopify-, GS1-, Catalogus-, voorraad- en huishoudtabellen blijven onveranderd. De officiële Excel (alle vijf tabbladen) blijft daarnaast als afzonderlijk gecontroleerd GitHub-artifact bestaan.

Deze wijziging mag uitsluitend via de gebruikelijke Alembic-applicatieroute worden toegepast na de afzonderlijke PO-goedkeuring voor een daadwerkelijke runtime-/server- of productieactie. Geen deployment en geen bestaande database gewijzigd door CI.
