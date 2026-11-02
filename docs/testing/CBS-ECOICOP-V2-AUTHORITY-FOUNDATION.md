# CBS ECOICOPv2 – implementatie, eerste schemafase

Dit is de eerste **technische** stap na ontwerp-PR #640: een toevoegende CBS-authority.
Het is nog **geen** afgeronde artikelclassificatiefunctie of migratie van bestaande classificaties.

## Wat is toegevoegd

- `cbs_ecoicop_categories`: officiële 6-cijferige code **als tekst**, NL-naam, expliciete ouder, niveau, bronversie, bron-URL, SHA-256, geldigheid en toelichting. Ouders moeten expliciet uit de officiële bron worden vastgesteld, nooit uit cijferprefixen worden afgeleid.
- `global_product_cbs_classifications`: afzonderlijk bevestigde classificatie per centraal product, met versie, actor en herkomst.
- `global_product_cbs_history`: afzonderlijke historie (ook bij verwijderen van classificatie), onafhankelijk van de verwijderde productrij.
- Database-referentiële controle op CBS-bronversie/code; restrictieve PostgreSQL-schrijfbescherming volgens de bestaande onderhoudsbarrière.
- De migratie weigert een downgrade wanneer één van deze drie tabellen gegevens bevat.

**Nog niet:** invoeren van de 440 proefcodes als operationele authority, classificatie-API, rollencontrole, UI, migratie van Shopify of GS1, verwijdering van fysieke gegevens of activeren van product-equivalentie.

## Beslisgrens voor de vervolgimplementatie

De bestaande afgeleide proefreferentie `tools/taxonomy_proof5_references/cbs_ecoicop_v2_2026.json` bevat codes en namen, maar geen betrouwbaar gevalideerde hiërarchie. De officiële CBS-bijlage moet worden vergeleken en de ouder/niveau/bronmetadata moeten reproduceerbaar geverifieerd worden voordat er categorieën operationeel worden geladen.

CBS beschrijft bestedingen. Geen automatische omzetting van GS1 Brick, Shopify of CBS naar productidentiteit, barcode of fysieke gelijkwaardigheid. Een classificatie zonder eenduidig bewijs blijft `Niet geclassificeerd`.

Nieuwe migratie `20261102_01` volgt op `20261031_02` en wijzigt geen bestaande tabellen. Het draaien van migraties op een actuele PO-/serveromgeving vereist de daarvoor geldende afzonderlijke toestemming.

PR #639 blijft Draft en wordt pas inhoudelijk herschreven na implementatie van de CBS-vrije equivalentie- en Bijna-op-keten.
