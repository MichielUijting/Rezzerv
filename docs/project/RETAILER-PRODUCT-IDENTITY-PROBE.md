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
