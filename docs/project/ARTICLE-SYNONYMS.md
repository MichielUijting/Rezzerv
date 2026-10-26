# Artikelsynoniemen

PO-opdracht 26 oktober 2026. TEST_LEVEL_PROVISIONAL: L.

De nieuwe actie **Artikelsynoniemen** en route `/artikelsynoniemen` zijn beschikbaar
voor Superusers **of** actieve Frontteamleden. Beide mogen dezelfde suggesties
bevestigen. Reguliere huishoudrollen, Platformbeheerder-only en IP-owner-only
geven geen toegang. De API controleert de actuele serversessie en canonieke
`platform.external_products.view` / `platform.external_products.link_existing`
permissions, plus de speciale functionele rol. Er worden geen extra algemene
Catalogusbeheerrechten aan Frontteam toegekend.

De bron is uitsluitend centrale Cataloguskennis, nooit privéhuishoudartikelen.
Een actief centraal artikel komt in aanmerking met een geldige barcode of een
bevestigde centrale winkelartikelcode. Een winkelcode is altijd voorzien van de
winkelnaam; een winkelcode wordt nooit omgezet in een barcode. Artikelen zonder
code/barcode moeten eerst in Externe databases 2 worden aangevuld. Deze wijziging
voegt aan dat bestaande scherm geen nieuwe opslagroute toe.

De kandidaatselectie gebruikt de beproefde TF-IDF/cosine-baseline: woord-1/2-grams
en teken-3/5-grams, beide 50%, over Nederlandse naam en variant. Winkelwoorden
worden genegeerd. Er is geen Zalando-model/API en geen externe netwerkopvraag.
Een sparse index vermijdt een dense N×N-matrix. Kandidaten hebben minimaal 0,20
tekstovereenkomst en staan bij ten minste één artikel in de beste zeven. Dit is
uitsluitend een suggestiegrens, geen betrouwbaarheidsclaim. Er wordt op de hele
centrale set gezocht, niet uitsluitend op AH/Jumbo. Dezelfde GTIN of dezelfde
winkelcode is een exacte identiteit en geen synoniempaar. Bekende verschillende
GPC Bricks worden uitgesloten; ontbrekende kenmerken worden niet verzonnen.

De standaard DataTable toont artikel, code/barcode, voorgesteld synoniem,
code/barcode van dat synoniem, beide verpakkingsinhouden en overeenkomst.
Zoeken, sorteren, kolombreedtes en paginering volgen het gedeelde component
(10 per pagina). Selectie blijft over pagina's/filters bestaan. **Koppelen** is
de expliciete handmatige bevestiging voor maximaal 200 gekozen paren tegelijk.
Alleen aanvinken of het scherm openen schrijft niets. Vernieuwen wist de selectie.

De backend valideert ieder paar opnieuw tegen actuele suggesties en een
fingerprint van de getoonde productfeiten. Bij een verouderd/ongeldig paar wordt
de gehele bulk afgewezen met 409; bestaande selectie blijft zichtbaar zodat
vernieuwen bewust gebeurt. Herhaling met ongewijzigde feiten is idempotent.
Productrijen worden in vaste volgorde vergrendeld. De unieke gesorteerde
paaridentiteit voorkomt dubbele of omgekeerde relaties. Opgeslagen zijn actor,
tijd, methode, score en fingerprint. Een bevestiging verdwijnt uit de suggesties
en blijft na herladen bewaard.

Dit is een directe relatie tussen twee centrale producten. Er wordt geen
transitieve gelijkheid afgeleid: A↔B en B↔C bewijzen niet A↔C. GTINs, producten,
verpakkingen, household_article_id, Artikelgroepen, bonnen en voorraad blijven
zelfstandig bestaan. Deze eerste functie geeft Bijna op of boodschappen geen
nieuwe automatische aggregatie; de bestaande automatische consumptietypes
blijven daarvoor leidend. Een hoge tekstscore is geen bewijs voor dezelfde smaak,
bereiding of samenstelling; de gebruiker vergelijkt de zichtbare productgegevens.

Alembic maakt uitsluitend `article_synonym_links`, met foreign keys, unieke
paarvolgorde en onderhoudsschrijfbarrière. Downgrade verwijdert alleen deze
nieuwe relaties. Bestaande catalogus-/huishoudgegevens worden niet teruggevuld.
Catalogusverwijdering verwijdert gekoppelde relaties via FK cascade.

Validatie: `backend/tests/test_article_synonyms.py` dekt ranking, identiteiten,
codegrens, beide rollen, ontbrekende rechten, requestgrenzen, stale bulk,
idempotentie, actoropslag en geïsoleerde migratie/downgrade. De eigen gefocuste
CI draait deze tests. De toegevoegde Playwright-spec draait in het bestaande
frontend-regressiecommando en dekt 390/1280 px voor beide rollen, selectie over
pagina/filter, foutbehoud, expliciete bulk, reload en weigering regulier account.
De bestaande PostgreSQL-foundation-, onderhouds-, rollen-, identity- en F7-gates
blijven aanvullend vereist; synthetische tests vervangen die niet.
