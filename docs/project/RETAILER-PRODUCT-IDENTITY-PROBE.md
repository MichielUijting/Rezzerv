# Winkelproductidentiteit: alleen-lezen bronproef

TEST_LEVEL_PROVISIONAL: L

## Correctie bronproef V2

Het eerste lokale rapport bevat 519 bronbonnen, waarvan 517 overgeslagen en
slechts 2 uitgelezen (9 bronregels). Dat is geen bruikbaar dekkingsbewijs.
V1 maakte geen onderscheid tussen ontbrekend bestand, opslagpad, hashconflict en
onbekende JSON-/bonstructuur. V2 telt deze oorzaken apart met vaste veilige labels.
Geen bestandspaden, tokens of inhoud van foutmeldingen worden afgedrukt.

V1 sloeg ook de telling van opgeslagen productcodes over bij een bronleesfout.
V2 leest die onafhankelijk: een bronbestandprobleem betekent niet dat er geen
productcodes zijn opgeslagen. Numerieke AH-/Picnic-winkel-ID's worden als
winkel-ID herkend, nooit als GTIN. De ondersteunde regelvelden en wrappervolgorde
volgen nu de bestaande retailer-normalizer, inclusief entries/receiptLines/basketItems.
De oorzaak van de 517 bronleesfouten is nog niet vastgesteld; V2 stelt die vast
zonder bestandspaden aan te passen, hashes te omzeilen of bestanden te herstellen.

Doel van deze eerste stap is vaststellen welke identificerende gegevens de
bestaande digitale bonkoppelingen werkelijk bewaren. Dit is geen geïmplementeerde
assortimentimport, websitezoeker of automatische Cataloguskoppeling.

## Gebruik

Start de bestaande Inhuis-omgeving op de gebruikelijke manier. Voer daarna het
bijgeleverde `Inhuis_Winkelproduct_Bronproef.cmd` uit. Het script gebruikt de
bestaande Compose-backend en PostgreSQL-database, zonder Git-switch, installatie,
containerstart, migratie of wijziging van bonnen. Het TXT-rapport staat in Downloads
en het venster blijft open. De proef werkt onafhankelijk van PR #603 en #605;
die bestaande PR's hoeven hiervoor niet opnieuw gestart of opgeschoond te worden.

De embedded onderzoekscode is identiek aan
`scripts/diagnostics/retailer_product_identity_probe.py`. Zij importeert geen
applicatiestartup en gebruikt een PostgreSQL REPEATABLE READ-transactie met
`SET TRANSACTION READ ONLY`, querytimeout en locktimeout.

## Wat de proef vaststelt

- Per winkel en per tijdelijk gepseudonimiseerd huishouden: aantallen opgeslagen
  digitale bronbonnen, bronregels en beschikbare identificatietypen.
- Expliciete EAN/GTIN/barcodevelden: alleen ASCII-cijfers met juiste lengte en
  controlecijfer tellen als structureel geldige codes. Dat bewijst nog niet dat
  de code het juiste product identificeert.
- `codeInput` en `productCode` blijven ambigu, ook met een geldig controlecijfer.
  Korte codes en winkel-ID's worden nooit aangevuld of tot GTIN gepromoveerd.
- AH/Picnic-ID's en geneste product-ID's blijven winkelartikelnummers.
- Tegenstrijdige of ongeldige expliciete barcodes worden apart geteld.
- Opgeslagen actieve, voorraadgerechtigde productregels worden afzonderlijk
  geteld. Zij worden niet op regelpositie of naam aan oorspronkelijke bronregels
  gekoppeld: tijdens import kunnen bijvoorbeeld gewichtsregels worden samengevoegd.
- Bronbestanden moeten binnen de geconfigureerde raw-opslag staan, kleiner zijn
  dan 8 MiB en exact dezelfde SHA-256 hebben als de databaseverwijzing.
- De proef leest maximaal 2000 bronbonnen. Meer bonnen geeft een veilige stop,
  geen ongemelde steekproef. Bronfouten worden apart geteld.
- Geen aankopen, prijzen, artikelnamen, barcodes, accounts, tokens, paden of echte
  huishoud-/bon-ID's in de uitvoer. Huishoudreferenties verschillen per uitvoering.

De selectie bevat historische opgeslagen retailerbronbonnen, ook na verwijdering
uit de actieve werklijst. Foto/PDF/e-mailbonnen vallen buiten deze bronproef.
Een winkel zonder bronbonnen wordt expliciet als niet onderzocht gemeld.

## Ontwikkelbronnen en begrenzing

| Winkel | Onderzochte ontwikkelbron | Vervolg dat nog live bewezen moet worden |
| --- | --- | --- |
| AH | https://github.com/gwillem/appie-go en https://github.com/salujayatharth/ah-api | Relatie bon-ID → catalogus-ID → expliciete GTIN; accountkoppeling bestaat al |
| Jumbo | https://github.com/vghoost360/Jumbo-API | Onze huidige bridge leest de bonweergave; productidentiteit is nog niet rechtstreeks bewezen |
| Lidl | https://github.com/Andre0512/lidl-plus en https://pypi.org/project/lidl-plus/ | `codeInput` kan scanner-/interne code zijn; bevestiging op productniveau vereist |
| Picnic | https://github.com/MRVDH/picnic-api en https://pypi.org/project/python-picnic-api2/ | Product-/bestel-ID naar EAN; geen live accountbewijs beschikbaar |
| Aldi NL | https://github.com/Repsay/supermarket-mobile-api-connector | Actuele cataloguswerking en barcodebeschikbaarheid; geen digitale bonroute bewezen |

Pakketten worden niet automatisch geïnstalleerd of uitgevoerd. Een repository die
alleen een README met een verwijzing naar een betaalde scraper bevat is geen
gevalideerde open-source connector. De oude PyPI `python-picnic-api`-release uit
2021 is geen bewijs van actuele werking. `appie-go` heeft een AGPLv3-licentie;
de implementatie kopieert daar geen code uit.

De Jumbo-voorbeeldoplossing kent vergelijkbaarheidsscores tussen **verschillende**
EAN's. Dat mechanisme mag nooit als exacte barcode-identiteit worden overgenomen.
PrijsProfeet is aanvullend te onderzoeken, maar aanbiedingen en gerapporteerde
EAN-dekking zijn geen bewijs van een volledig of historisch winkelassortiment.

Na het lokale rapport kan de volgende bronstap gericht worden gebouwd. Pas een
echte productrespons met dezelfde betrouwbare winkel-ID en expliciete GTIN kan de
directe verbinding bewijzen. Naam-/winkel-/merk-/inhoudmatches blijven suggesties.
OFF blijft de afgesproken terugval. Er is geen productieroute of startup-hook naar
deze diagnosemodule; geen Catalogus-, huishoudartikel- of voorraadmutatie.

Geen applicatieversiebump: uitsluitend geïsoleerde diagnose-/testcode en
documentatie; de applicatieruntime blijft ongewijzigd.

## Online catalogusproef

`scripts/diagnostics/Inhuis_Winkelproduct_Onlineproef.cmd` gebruikt de opgeslagen
actieve productregels rechtstreeks. Ontbrekende oude bronbestanden blokkeren deze
proef niet. Er worden maximaal twee verschillende artikelen per AH/Lidl/Jumbo
geselecteerd, met canonieke productrol en dezelfde huishoudrelatie in alle joins.
Deze openbare productkennis wordt uitsluitend binnen de lokale proef vergeleken;
er worden geen huishoudartikelen samengevoegd of blijvende koppelingen gemaakt.
De databaseverbinding/snapshot wordt vrijgegeven vóór externe verzoeken.

- AH: anoniem token, productzoeken met boncode en zo nodig naam; uitsluitend
  `hqId` wordt vergeleken met de boncode. De aparte `webshopId` bepaalt de
  GraphQL-productlookup. De response moet dezelfde webshop-ID teruggeven. Een
  GTIN komt uitsluitend uit het expliciete `product.tradeItem.gtin`-veld.
- Lidl: Nederlandse `/q/api/search` met `q`, `assortment=NL`, `locale=nl_NL` en
  verplichte `version=2.0`. Zoekfallback kan ongerelateerde producten retourneren;
  naam-/variantcontrole wijst die af. ERP/webshop-ID's worden niet met boncodes
  vereenzelvigd: alleen een expliciete exact overeenkomende IAN telt als observatie.
  Een eventuele GTIN komt uit één passend JSON-LD Product op de productpagina,
  niet uit willekeurige cijfers, aanbiedingen of aanbevelingen elders op de pagina.
- Jumbo: openbare zoekpagina → expliciete productlink/SKU → product-GraphQL.
  Bij 401/403 wordt alleen de openbare productpagina geprobeerd, zonder login,
  cookies of accountomweg. Het JSON-LD Product moet dezelfde SKU hebben. Zonder
  boncode blijft een gevonden barcode uitsluitend een naamsuggestie.
- Picnic blijft expliciet niet getest zonder account. De oude Aldi-app-API is
  geen geverifieerde actuele connector en is niet geactiveerd.

De proef deelt alleen naam/boncode met de betreffende winkelzoekfunctie, geen
bonbedragen, datums, huishouden-ID's of klantgegevens. Het TXT-rapport bevat alleen
aantallen en vaste status-/foutcodes, geen tokens, codes, namen of privébestanden.
HTTPS-hosts zijn vast begrensd; redirects, mutaties en accountacties zijn geweigerd.
Maximaal 24 verzoeken, elk maximaal 8 seconden, totaal netwerkbudget 120 seconden,
maximale response 8 MiB. Geen retries of betaalde proxies. De CMD gebruikt dezelfde
bewezen bestaande-runtimecontrole als de lokaal geslaagde bronproef.

Status `receipt_code_and_catalog_gtin_observed` betekent alleen dat dezelfde code
in het benoemde winkelveld en een expliciete GTIN samen zijn waargenomen. Het is
geen automatische Cataloguskoppeling, acceptatie of assortimentdekkingsclaim.
Conflicterende barcodes worden niet gekozen. Een overeenkomstige naam zonder
overeenkomstige boncode blijft `name_suggestions_only`. Een geweigerde bron is
`source_unavailable`, nooit een claim dat het artikel niet bestaat.

Live protocolcontrole 25 oktober 2026 met een openbaar voorbeeldproduct:
AH `hqId` → webshopproduct → `tradeItem.gtin` werkte. Lidl gaf bij halfvolle melk
ook ongerelateerde producten terug; de nieuwe filter wees de onderzochte resultaten
af. De Jumbo-product-API gaf 401; de openbare JSON-LD-terugval leverde vervolgens
twee passende catalogusproducten met expliciete GTIN op, uitsluitend naamsuggesties.
Dit zijn protocolobservaties uit deze omgeving, nog geen bewijs op de PO-database.
Windows/CMD en de echte PostgreSQL-selectie moeten lokaal worden uitgevoerd.

De volgende PO-stap is de Onlineproef uitvoeren bij draaiend Inhuis en het rapport
`Inhuis_Winkelproduct_Onlineproef_Resultaat.txt` delen. De bronproef hoeft niet opnieuw.
Productieruntime/Externe databases 2 verandert pas nadat de werkelijke bronroute is
bewezen; deze proef schrijft geen barcodes of Catalogusproducten.
