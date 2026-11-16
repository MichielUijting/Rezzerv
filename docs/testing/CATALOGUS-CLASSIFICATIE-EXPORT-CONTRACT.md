# Inhuis Catalogusclassificatie-export v1

TEST_LEVEL_PROVISIONAL: L. Scope: alleen lezen en download; geen import, datawijziging,
migratie, AI-/classificatie-toekenning of productieactie.

## Formaat en toegang

Artikelbeheer toont **Catalogus exporteren** voor de platform-Superuser (systeemcontext)
en Frontteamleden (reguliere context) met `platform.external_products.view`.
De backend controleert de bevoegdheid opnieuw via de bestaande canonieke
`_actor`-autoriteit op `GET /api/cbs-classifications/catalog-export`.
Geen browser-aangeleverde rol- of huishoudidentiteit. Geen muterende GET.
Response: ZIP (application/zip), no-store, Content-Disposition attachment.
PostgreSQL leest één transactionele READ ONLY REPEATABLE READ-snapshot.

## Complete, herleidbare bron

ZIP is één download voor ChatGPT, met exact zeven bestanden:

1. `catalogus.csv`: één regel per niet-verwijderd `global_products.id`, ook
   ongeclassificeerde, inactive en GTIN-loze artikelen. Productgegevens,
   bestaande GS1 GPC-Brickcode + Nederlandse labels + herkomst, actieve CBS
   ECOICOPv2-code + omschrijving/bronversie/herkomst/versie. Drie lege
   voorstelvelden voor ChatGPT; geen classificatie wordt toegekend.
2. `bevestigde_matches.csv`: enkel `external_article_product_links.status =
   confirmed` en expliciet bevestigde `ed2_receipt_family_links`, met hun
   centrale product-ID en bonnaam/winkelcode/bonartikelnummer; geen echte
   kassabon-, aankoop-, huishoud- of voorraadregistraties.
3. `bevestigde_synoniemen.csv`: expliciet bevestigde directe centrale
   `article_synonym_links`, met beide stabiele product-ID's.
4. `gpc_referentie_nl.csv`: bestaande actieve officiële NL-GPC-referentie.
5. `cbs_referentie.csv`: aanwezige officiële ECOICOPv2-codehiërarchie inclusief
   `is_leaf`; niet-eindcategorieën zijn geen bevestigbare classificaties.
6. `manifest.json`: formaatversie, UTC, volledige regeltellingen en expliciete
   bevestiging dat import nog niet beschikbaar is.
7. `LEESMIJ.txt`: gebruiksinstructies en interpretatiegrenzen.

Tekstexport met UTF-8 BOM, vaste puntkomma-scheiding en volledige quoting;
formule-achtige gebruikersvelden worden geneutraliseerd. Voorloopnullen
blijven als ruwe tekst bewaard in de CSV; bij handmatige Excel-invoer altijd
als *tekst* importeren, om automatische nummerconversie te voorkomen.

`snapshot_sha256` is een unieke productrijvingerafdruk voor een eventuele
toekomstige afzonderlijke import-PR. Het is geen recht op een automatische
wijziging; huidige bestaande waarden zijn alleen-lezen.

## Grenzen en regressie

Niet verzamelen: persoonlijke bonnen, huishoudgegevens, gebruikersnamen,
actor-ID's, voorraad, foto's, suggestieparen, externe OFF-bulkdatabase of
tussentijdse kandidaatmatches. Geen naamscore/GTIN wordt aangemerkt als
bevestigde synoniemrelatie. Verwijderde producten en hun relaties worden
niet geëxporteerd; geen impliciet dedupliceren op naam.

Regressies controleren autorisatie, vorm/inhoud/download, matchstatus,
onbevestigde relaties, geen DB-writes, niet-verwijderde volledigheid,
oude en bestaande classificaties, CSV-formuleveiligheid en de
frontend-navigatie. De vervolgstap *Importeren* vereist een nieuwe
expliciete PO-opdracht, validatie van de actieve source/snapshot en
bevoegde expliciete bevestiging; niet geïmplementeerd in deze PR.

STYLEGUIDE_IMPACT: updated
STYLEGUIDE_REASON: bestaand Button en Melding; één aparte
Catalogus-exportactie in Artikelbeheer.
