# Inhuis — gecontroleerde GS1/CBS-classificatie-import vanuit spreadsheet

TEST_LEVEL_PROVISIONAL: L
STYLEGUIDE_IMPACT: updated
STYLEGUIDE_REASON: Hergebruik van standaard Button, DataTable en de centrale Melding-overlay in Classificeren; geen nieuwe dialoogvarianten.

## Aanleiding en broncontract
Het PO-bestand `Inhuis_Catalogus_Classificatievoorstellen_20261116.xlsx` bevat
vier werkbladen: Leeswijzer, Alle artikelen, Controle bestaand en Voorgestelde codes.
**Alle artikelen** (617 regels in het bronbestand) is de enige importautoriteit.
CSV tegenhanger heeft dezelfde 23 kolommen in `snake_case`, UTF-8 en
puntkommascheiding. Product-ID en `snapshot_sha256` uit de eerdere
Catalogusexport zijn de identiteitsankers, nooit naam of GTIN alleen.

Hoge, middelhoge en handmatig te beoordelen voorstellen zijn alle
**suggesties**, geen bevestigde classificaties. Het huidige bestand bevat
276 GS1-voorstellen hoog, 443 CBS hoog, 41 CBS middel en 30 te controleren
bestaande GS1-classificaties. De backend gebruikt uitsluitend actueel officiële
NL-GS1-Bricks en laagste officiële CBS ECOICOP-categorieën; een omschrijving in
Excel is nooit het autoriteitsbewijs voor een code.

## Scherm en gebruik
Alleen na Artikelbeheer → **Classificeren** zijn de twee standaardacties
**Catalogus exporteren** en **Classificaties importeren** zichtbaar.
Importeren start met Excel (.xlsx) of CSV en een expliciete read-only preview.
De importwerkvoorraad bevat **uitsluitend** artikelen waarvoor ten minste één
voorgestelde officiële GS1 GPC- of CBS ECOICOP-code anders is dan de **actuele**
classificatie. Een gelijke code wordt niet getoond, ook niet als Excel
"Bestaand - controle nodig" meldt. Afwijkingen worden per classificatiesysteem
uitgesplitst in **Nieuw** en **Anders dan bestaand**, met code, omschrijving,
status en onderbouwing. Geen voorstel of dezelfde code als de actuele code
betekent geen importtaak; meerdere verschillende voorstellen voor één systeem
worden niet automatisch gekozen maar als blokkade getoond.

De bestaande DataTable blijft de paginerings-, sorteer- en filterautoriteit
(8 regels per pagina). De selectie kent drie duidelijk gescheiden onderdelen:
een checkbox per artikelrij, een **checkbox zonder kolomtitel** in de eerste
tabelkop die uitsluitend de **zichtbare pagina** (de)selecteert, en een apart
gelabelde checkbox **Alle rijen in de tabel** direct **rechtsboven de tabel**.
Dit laatste vak selecteert alle selecteerbare rijen die voldoen aan de actuele
zoek-, weergave- en kolomfilters, **ook op andere pagina's**. Beide bulkselecties
slaan geblokkeerde of niet-bevoegde rijen over, worden vanzelf aangevinkt als
hun volledige toepasselijke selectie geselecteerd is, en schakelen bij opnieuw
klikken uitsluitend die toepasselijke selectie uit. Selecties op andere
pagina's blijven bewaard wanneer alleen de paginacheckbox wordt gewijzigd.
Er staat geen kolomtitel **Selecteer**. Rijselectie betekent: verwerk alle
veilige nieuwe/afwijkende GS1- en CBS-voorstellen van dat artikel tezamen.
De verwerking gebeurt met de primaire bulkknop **Geselecteerde rijen verwerken**
rechts **onder de tabel**, bij de standaardpaginering. De **verwerkingsgrens
is 100 volledige artikelrijen**, niet 100 afzonderlijke codes. Een artikel kan
één GS1- en één CBS-wijziging bevatten: maximaal 200 classificatiebeslissingen
per batch. Een rij wordt nooit tussen twee batches gesplitst.

Bij een selectie van meer dan 100 artikelrijen is de verwerkingsknop **wel
beschikbaar**. Direct na de brede selectie verschijnt de centrale
**blijvende keuze-overlay** met **Eerste 100 rijen verwerken** en **Annuleren**.
De eerste 100 **geselecteerde** artikelen volgen de actuele gefilterde en
gesorteerde tabelvolgorde; eerder geselecteerde maar niet meer zichtbare
artikelen komen daarna, zodat zij niet onopgemerkt verdwijnen. De overlay
blijft aanwezig tot een expliciete actie of klik buiten het venster; er is
**geen automatische tijdslimiet**. Annuleren of buiten het venster klikken
schrijft niets en behoudt de selectie. Ook na annuleren blijft de bulkknop
beschikbaar om de beslissing opnieuw te openen.

De centrale Melding-overlay toont de exacte aantallen toe te voegen én te
vervangen GS1-/CBS-classificaties **van de eerste batch** en vraagt vóór
iedere batch expliciete toestemming. De import verwerkt die maximaal 100
artikelen samen in één transactie; bij succes blijven de nog geselecteerde
artikelen zichtbaar/geselecteerd voor een volgende batch. Bij een mislukte
batch wordt niets van die batch verwerkt. Selecteren zelf schrijft nooit
gegevens. Er zijn geen
checkboxes of code-keuzelijsten midden in de tabel, geen automatische
classificatietoekenning en geen stille overschrijving.

## Centrale Cataloguswerkvoorraad onder Classificeren
De onderste classificatietabel bevat **alle niet-verwijderde centrale
Catalogusproducten**; zij is niet gelijk aan de importpreview en meet niet of
ChatGPT voor een product een voorstel had. De teller open classificatietaken
telt ontbrekende GS1 en ontbrekende CBS per product **afzonderlijk**.
Een lege importpreview betekent slechts dat het huidige voorstelbestand geen
nieuwe of afwijkende verwerkbare codes meer aanbiedt.

De bestaande gedeelde DataTable blijft verantwoordelijk voor zoeken, filters,
sortering en paginering (8 rijen per pagina). Selectie is uitsluitend voor
**export**: een rijcheckbox, een selectievak zonder kolomtitel in de eerste
tabelkop (alleen de zichtbare pagina) en de apart gelabelde checkbox
**Alle rijen in de tabel** direct rechtsboven (alle rijen in de actuele
zoek-/kolomfilters, ook op andere pagina's). Selecties buiten een filter
blijven geselecteerd, ook bij een paginawissel. De teller noemt het totale
aantal geselecteerde artikelen; **Selectie wissen** en **Geselecteerde rijen
exporteren** staan onder de tabel bij de standaardpaginering.

De browser exporteert een UTF-8/semicolon CSV met BOM en afgeschermde
spreadsheet-formules. Het bestand bevat uitsluitend de geselecteerde
Catalogusproduct-ID's, naam, merk, barcode, actuele GS1-/CBS-code,
CBS-omschrijving/referentie en geclassificeerd-status, over alle pagina's.
Er is geen backend-POST en er worden geen Catalogus- of huishoudgegevens
gewijzigd. De export is **een onderzoeks-/werklijst** en geen directe
importautoriteit: de 23 importvelden en actuele `snapshot_sha256` ontbreken.
Gebruik voor een latere officiële import opnieuw de Catalogusexport en de
bestaande preview-/goedkeuringsroute.

## Backendveiligheid
- Preview: alleen lezen, PostgreSQL REPEATABLE READ READ ONLY, controle van
  bestandsformaat, kolommen, unieke product-ID's en controlehashes.
- Beveiliging: ingelogde bevoegde gebruiker, bestaande
  `platform.external_products.view` voor preview,
  `platform.external_products.link_existing` voor bevestiging en aanvullend
  `platform.gpc.update` wanneer de batch GS1 schrijft; backend bepaalt identiteit.
- Geen onbewezen automatisch koppelen op naam of synoniemen.
- Per bevestigde batch maximaal 100 unieke product-ID's en maximaal
  200 unieke (product-ID, systeem)-keuzes. De backend controleert beide grenzen
  onafhankelijk en valideert actuele productnaam, snapshot, bestaande code,
  officiële referentie en expliciete vervangingskeuze.
- Eén transactie: óf alle geselecteerde GS1/CBS-wijzigingen worden opgeslagen
  óf geen enkele. CBS gebruikt de bestaande `confirm_cbs_batch` en
  versie-/historiecontroles. GS1 gebruikt de bestaande canonieke
  `global_product_gpc_bricks` met `assignment_source =
  explicit_classification_import`. Bestaande zonder vervangingsakkoord
  worden niet overschreven.
- De oorspronkelijke export- of Excelinformatie verandert nooit zelf
  de database. Geen household data, voorraad, kassabon- of
  catalogusproductkoppelingen in scope.

## Acceptatiebewijs en afhankelijkheid
Export-PR #691 is gemerged in main. Deze import blijft als zelfstandige
Draft-PR #692 open. Controleer de zes versiebronnen, normale/preflight- en
F7 Full exact-candidate-controles op de definitieve importkandidaat,
laat de PO lokaal accepteren en verkrijg **afzonderlijke expliciete merge-GO**.
Een goedgekeurd Excelbestand is geen merge- of productie-GO.

Tijdens importcontrole toont elke GS1/CBS-keuzelijst ook de oorspronkelijke
status en de indicatieve onderbouwing uit de spreadsheet, zodat de gebruiker
nooit alleen op basis van een codenummer hoeft goed te keuren.
