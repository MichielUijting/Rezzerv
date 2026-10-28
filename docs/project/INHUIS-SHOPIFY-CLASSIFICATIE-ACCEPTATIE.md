# Shopify-classificatie: beoordeling van bestaande Catalogusartikelen

## Afbakening
Alleen de al bestaande checksum-geldige primaire Catalogus-GTIN mag worden beoordeeld. Geen bonartikelnummers, barcodeherleiding, nieuwe productidentiteit, GS1/GPC-mutatie, Artikelgroep, Producttype, kassabon, voorraad of huishoudenwrites. Shopify v2026-08 NL is een zelfstandige, licentievrije taxonomie en géén barcode- of identiteitstabel. CBS is geen bindende classificatie. OFF is uitsluitend een op verzoek geraadpleegde voorstelbron, nooit beslisautoriteit.

## Bevoegdheden en opslag
De actuele **server**sessie verleent Superuser in system-context of Frontteam in regular-context uitsluitend via reeds bestaande platform.external_products.view/search/link_existing-permissies toegang. Een Frontteamlid krijgt geen algemene Catalogusbeheerrechten. Het scherm bevat de gedeelde DataTable, de centrale Select en aparte barcodebevestiging voordat Bulk bevestigen beschikbaar is.

Alembic maakt global_product_shopify_classifications en global_product_shopify_history. Bevestigingen bewaren categorie-ID, categoriepad, taxonomieversie, oude bestaande barcode, actor, timestamp en stijgend versienummer. Eén bulk bevat maximaal 100 verschillende product-ID's. De server valideert alle barcodes en categorieën opnieuw, vergrendelt centrale producten in vaste volgorde, vergelijkt de verwachte opgeslagen versie en schrijft alles in één transactie. Iedere afwijking geeft 409/422 en volledige rollback. PostgreSQL-onderhoudsbarrière beschermt beide tabellen; downgrade stopt als er al data bestaat. Auditgeschiedenis heeft geen cascade-FK zodat historische acties niet stil kunnen verdwijnen.

## Gekende beperkingen
De referentie wordt hergebruikt uit de in proef 7 gebundelde tools/taxonomy_proof5_references. Als die in een deployment niet read-only aanwezig zijn, antwoordt de API 503 en slaat niets op. OFF wordt uitsluitend op verzoek opgezocht, in één backendproces maximaal eenmaal per zes seconden. Meerdere backendworkers hebben nog geen gedeelde quotaregeling. Voor structureel OFF-hergebruik is de ODbL-hergebruikstoets vóór productie nodig. Bij een nieuwe Shopify-taxonomieversie is expliciete migratie/herbeoordeling nodig.

## Vereiste QA vóór Ready
Gerichte backend/rol/GTIN/rollback tests, daadwerkelijke PostgreSQL-Alembic upgrade/downgrade en DML-only rechten, browser Playwright, frontendbuild, volledige rollen-v2-matrix, versie/preflight en niveau-L F7 Full Regression op definitieve SHA. Niets in dit document vervangt uitgevoerde testbewijzen.

TEST_LEVEL_PROVISIONAL: L
Reden: centrale schema-, autorisatie- en UI-wijziging.

Draft boven proef 7 (#621). Andere open onderliggende PR's (#616–#620) worden niet aangepast. Niet mergen of deployen zonder afzonderlijke expliciete PO-toestemming.
