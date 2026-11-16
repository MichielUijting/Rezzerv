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
(8 regels per pagina). De **enige checkboxes** zijn de rijselectie en **Alle rijen in de tabel**
in de eerste kolomkop; er staat géén kolomtitel **Selecteer** en geen
afzonderlijk selectievak boven de tabel. De kopcheckbox selecteert alle
selecteerbare rijen die aan de actuele zoek-, weergave- en kolomfilters voldoen,
**ook op andere pagina's**, en schakelt die selectie weer uit. Niet-selecteerbare
regels worden niet geselecteerd. Rijselectie betekent: verwerk alle
veilige nieuwe/afwijkende GS1- en CBS-voorstellen van dat artikel tezamen.
De verwerking gebeurt met de primaire bulkknop **Geselecteerde rijen verwerken**
rechts **onder de tabel**, bij de standaardpaginering. Maximaal 100
classificatiecodes per batch, zonder één artikel tussen twee batches te splitsen.
Bij een selectie van meer dan 100 codes blijft de bulkactie uitgeschakeld;
de gebruiker krijgt een begrijpelijke centrale Melding en moet de selectie
verkleinen of filteren. Selecteren zelf schrijft nooit gegevens.
De centrale Melding-overlay toont aantallen toe te voegen én te vervangen
classificaties en vraagt expliciete definitieve bevestiging. Er zijn geen
checkboxes of code-keuzelijsten midden in de tabel, geen automatische
classificatietoekenning en geen stille overschrijving.

## Backendveiligheid
- Preview: alleen lezen, PostgreSQL REPEATABLE READ READ ONLY, controle van
  bestandsformaat, kolommen, unieke product-ID's en controlehashes.
- Beveiliging: ingelogde bevoegde gebruiker, bestaande
  `platform.external_products.view` voor preview,
  `platform.external_products.link_existing` voor bevestiging en aanvullend
  `platform.gpc.update` wanneer de batch GS1 schrijft; backend bepaalt identiteit.
- Geen onbewezen automatisch koppelen op naam of synoniemen.
- Per bevestigde batch maximaal 100 unieke (product-ID, systeem)-keuzes,
  validatie van de actuele productnaam, snapshot, bestaande code, officiële
  referentie en eventueel expliciete vervangingskeuze.
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
Deze import is een afzonderlijke gestapelde Draft-PR boven de nog niet
gemergde export-PR #691. Eerst #691 afzonderlijk volgens eigen gates
afhandelen, daarna de import-PR op de dan actuele main herbaseren/synchroniseren,
zes versiebronnen controleren, normale en F7 Full exact-candidate controleren,
functioneel lokaal accepteren en **afzonderlijke expliciete merge-GO** verkrijgen.
Een goedgekeurd Excelbestand is geen merge- of productie-GO.

Tijdens importcontrole toont elke GS1/CBS-keuzelijst ook de oorspronkelijke
status en de indicatieve onderbouwing uit de spreadsheet, zodat de gebruiker
nooit alleen op basis van een codenummer hoeft goed te keuren.
