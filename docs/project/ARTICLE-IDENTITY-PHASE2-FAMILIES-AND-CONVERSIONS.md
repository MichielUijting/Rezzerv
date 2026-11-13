# Inhuis — fase 2B: geteste productfamilie en exacte verpakkingseenheden

**TEST_LEVEL_PROVISIONAL: L**. Gebaseerd op het PO-doelontwerp
ARTICLE-IDENTITY-FUNCTIONAL-DESIGN-v2.md, besluiten 5, 6B, 10B,
13B, 15A, 17B, 23A en 25A.

## Veilig toegestane semantische familie
Alleen **verse courgette** (courgette/courgettes, biologisch/bio,
groen en geel) heeft nu een expliciete geteste whitelist. Beide
Catalogusartikelen moeten daar afzonderlijk volledig aan voldoen.
Diepvries, babyvoeding, soep, maaltijdmix, voorgesneden, kruiden,
aantal of onbekende bijvoegingen maken geen automatische sterke kandidaat.
Winkel, merk, categorie en bontekst gelden nooit als familie-identiteit.

Wanneer beide bekende verpakkingshoeveelheden gelijk zijn, toont de
bestaande synoniemenbeoordeling Sterke kandidaat. Dat is enkel een
leesadvies. Een koppeling vereist nog steeds expliciet Koppelen, plus
de bestaande identity-, GPC/CBS-, transitive-, rol- en auditcontrole.

## Exact toegestane hoeveelheidsverhoudingen
Alleen expliciet bewaarde Catalogusvelden size_value en size_unit zijn
de input: 1 kg = 1000 g, 1 l = 1000 ml, stuk = stuks.
Alleen gelijke dimensies worden vergeleken. De breuk is exact:
1 linker verpakking tegenover een rechter verpakking (bv. 250 g
tegenover 500 g = 1/2). Een ratio buiten 1/1000 t/m 1000,
een ongeldige/ontbrekende hoeveelheid en onbekende eenheden zijn
niet converteerbaar. Een stuksomrekening levert nooit gram op.
Geen schattingen op grond van naam, prijs, foto, gewichten van
gemiddelde stuks, volumegewicht of verborgen voedingskenmerken.

Een echte verpakkingsafwijking blijft Controleren, ook bij een bekende
exacte factor. De factor is alleen uitleg, geen automatische afboeking,
geen wijziging van bestaande bevestigde relaties en geen historische
bron- of voorraadmutatie. Fase 3 moet eerst afzonderlijk besluiten
hoe een geautoriseerde, huishoudspecifieke afboeking van zulke
hoeveelheden verantwoord kan gebeuren.

Permanente regressies toetsen familie-whitelist, uitsluitingen,
factoren, onbetrouwbare maten en bestaande scheiding van gebruikersdata.
Nog open: uitbreiding met afzonderlijk geteste/goedgekeurde families en
een gevolgenpreview op groepsniveau. De finale PR vereist risiconiveau L,
preflight, correcte versie en exact-candidate F7. Merge en deployment
vereisen afzonderlijke expliciete PO-GO.

## PO-geconstateerde kandidaatfout: AH Courgette / Olvarit

Hersteld: tekstovereenkomst kan een geteste verse productfamilie niet langer
als automatisch voorstel aan babyvoeding/diepvries koppelen. Bekende
semantische tegenstrijdigheden worden al in de voorstelgenerator
geweigerd; de bestaande manuele browse blijft behouden. Het rechterpaneel
toont nu het verschil tussen voorstellen en overige doorzoekbare
Catalogusartikelen. Er wordt bij bekijken niets opgeslagen.

Apart op te lossen: Identificeren kan een reeds bevestigde winkelgebonden
barcode met een actief Catalogusproduct vastleggen terwijl de huidige
Synoniemen-projectie die identificatiebron nog niet leest. Dat is geen
bewijs van een ongeldige barcode. Aanpassing vergt een gecontroleerd
identiteit/projectiecontract en aparte regressie; geen automatische
herinterpretatie van winkelcodes als mondiale GTINs.
