# Inhuis UI-styleguide

Status: **canonieke UI-bron** voor gebruikerszichtbare vormgeving en interactiepatronen in Inhuis.  
Laatst inhoudelijk vastgesteld door de PO: 17 september 2026.

Deze styleguide is de actuele leesbare UI-bron voor nieuwe schermen en wijzigingen aan bestaande schermen. Historische styleguidedocumenten blijven audittrail, maar nieuwe UI-beslissingen worden hier geconsolideerd. Bij een conflict met een oudere UI-notitie geldt deze canonieke styleguide, tenzij de PO expliciet een nieuwere afwijking heeft vastgesteld.

Historische besluiten die hierin zijn opgenomen:
- `docs/Rezzerv-Styleguide_v05.08.md`: knoptekst is niet vet;
- `Rezzerv-Styleguide_v05.14.md`: niet-numerieke tabelkolommen links, numerieke kolommen rechts, met gelijke uitlijning voor titel/filter/cellen.

## Ontwerpprincipes

Inhuis is:
- rustig en overzichtelijk;
- huiselijk en warm zonder decoratieve drukte;
- eenvoudig te begrijpen zonder technische voorkennis;
- mobiel eerst voor de kernflow;
- consistent: dezelfde functie ziet er op verschillende schermen hetzelfde uit.

Visuele hiërarchie ontstaat primair door positie, witruimte, gewicht, kleur en surface, niet door veel verschillende lettergroottes of losse schermspecifieke patronen.

## Typografie

Centrale tokens:
- `--font-family-base`: `Arial, sans-serif`
- `--font-size-ui-body`: `14px`
- `--font-size-ui-title`: `16px`

Regels:
- gebruikerszichtbare tekst gebruikt Arial;
- per applicatiescherm zijn exact twee tekstgroottes toegestaan;
- `14px` is de normale UI-maat voor labels, invoer, filters, knoppen, badges, metadata, tabeltekst en toelichtingen;
- `16px` is voor schermtitels, sectietitels en expliciete hoofdnadruk;
- extra hiërarchie komt uit gewicht, kleur en witruimte, niet uit een derde tekstgrootte;
- knoptekst gebruikt normaal gewicht (`font-weight: 400`) en is niet vet;
- titels/hoofdnadruk mogen semibold/bold zijn wanneer dat voor hiërarchie nodig is;
- decoratieve iconen en symbolen zijn geen tekst en mogen onafhankelijk worden geschaald;
- nieuwe UI-code introduceert geen derde gebruikerszichtbare tekstmaat.

## Kleuren

Centrale tokens:
- `--color-brand-primary`: `#1A3E2B` — donkere brand-ink voor tekst, iconen en focus op lichte surfaces;
- `--color-ui-primary`: `#008000` — primaire donkergroene UI-kleur voor dominante gekleurde surfaces;
- `--color-ui-primary-text`: `#FFFFFF` — tekst en iconen op primaire groene surfaces;
- `--color-brand-light`: `#D9F5E0`;
- `--color-text-primary`: `#1A1A1A`;
- `--color-text-inverse`: `#FFFFFF`;
- `--color-border-default`: `#CFE8D6`;
- `--color-table-grid`: `#8FD19E`.

Gebruik:
- `#008000` is de primaire Inhuis-UI-kleur voor header, primaire gekleurde acties, tabelheaders en de meldingenbalk;
- tekst en iconen op `#008000` zijn wit;
- `#1A3E2B` blijft de brand-ink voor tekst, iconen, focus/accent en geselecteerde status op lichte of witte surfaces;
- normale tekst gebruikt de primaire donkere tekstkleur;
- lichte groentinten zijn ondersteunend en concurreren niet met de primaire actie;
- de legacy-token `--rz-accent` wordt centraal gekoppeld aan `--color-ui-primary`;
- voeg geen nieuwe dominante merkkleur toe zonder expliciete PO-beslissing en styleguide-update;
- fout-, waarschuwing- en succeskleuren mogen semantisch afwijken, maar worden niet als alternatieve merkkleur ingezet.

## Spacing, radius en elevation

Centrale spacingtokens:
- `--space-xs`: `4px`
- `--space-sm`: `8px`
- `--space-md`: `16px`
- `--space-lg`: `24px`
- `--space-xl`: `32px`
- `--space-mobile-field-inline`: `1ch`

Centrale radiustokens:
- `--radius-sm`: `4px`
- `--radius-md`: `6px`
- `--radius-lg`: `14px`

Centrale elevationtokens:
- `--elevation-0`: `none`
- `--elevation-1`: `0 2px 6px rgba(0,0,0,0.10)`
- `--elevation-1-hover`: `0 4px 10px rgba(0,0,0,0.14)`
- `--elevation-2`: `0 10px 24px rgba(0,0,0,0.18)`
- `--elevation-3`: `0 18px 40px rgba(0,0,0,0.28)`

Regels:
- nieuwe gedeelde componenten gebruiken waar mogelijk de centrale tokens;
- willekeurige bijna-gelijke spacing- of radiuswaarden worden niet als nieuwe standaard toegevoegd;
- op mobiel hebben veldachtige rijen links en rechts standaard ongeveer één teken (`1ch`) interne ademruimte; bestaande grotere padding van echte invoervelden blijft behouden;
- de `1ch`-binnenmarge hoort bij de mobiele rijcomponent zelf en blijft dus gelden bij browserzoom of responsive emulatie, onafhankelijk van CSS-breakpoints;
- als een bestaande afwijking wordt aangeraakt, wordt bewust gekozen: behouden als expliciete uitzondering of convergeren naar een centraal token.

## Schermopbouw

Voor mobiele kernschermen is de standaardvolgorde:
1. header;
2. zoeken/filteren/context;
3. hoofdinhoud in cards/lijst/tabel;
4. één dominante primaire actie waar nodig;
5. tijdelijke feedback uitsluitend in de centrale onderste meldingenbalk.

Alle onderdelen volgen één horizontale uitlijning en herhaalbare spacing. Een scherm introduceert geen eigen navigatie- of actiepatroon wanneer een bestaand centraal patroon beschikbaar is.

## Mobiele navigatie

Inhuis gebruikt op mobiel twee navigatieniveaus:
- hoofdmodules worden rechtstreeks geopend vanuit de centrale hoofd-/tabnavigatie;
- details en vervolgstappen liggen op een navigatiestack boven de module waaruit zij zijn geopend.

Voor de browserapp geldt:
- de browsergeschiedenis blijft leidend voor terugnavigatie;
- voeg geen schermspecifieke `navigate(-1)`, `history.back()` of hard gecodeerde terugactie toe zolang de webapp in de browser draait;
- een detailroute wordt normaal via routing geopend;
- terugkeren naar een lijst hoort zoek-/filter-/sorteringscontext en scrollpositie zo veel mogelijk te behouden.

Voor een native mobiele shell geldt hetzelfde route-/stackmodel, maar zonder zichtbare browserbediening:
- terugpijl, iOS edge-swipe en Android systeem-back voeren semantisch dezelfde stap terug uit;
- terug betekent terug naar de herkomstcontext en niet naar een hard gecodeerde hoofdmodule;
- een sprong naar een hoofdmodule is een modulewissel en geen terugactie.

## Header en branding

- standaard headerhoogte: `58px` op grotere schermen en `64px` op mobiel;
- achtergrond: `--color-ui-primary` (`#008000`);
- schermtitel en subtitel gebruiken wit (`--color-ui-primary-text`);
- gebruikerszichtbaar merk is **Inhuis**;
- het witte Inhuis-logo staat rechts, is verticaal gecentreerd en blijft volledig binnen de header;
- interne technische naamgeving `Rezzerv` mag in code blijven maar wordt niet als gebruikersmerk getoond.

## Mobiele achtergrond en surfaces

De mobiele Voorraad-weergave is de visuele referentie voor de kernflow:
- lichtgroen, zacht gevlekt en laag in contrast;
- asset `/inhuis-green-wallpaper.svg`;
- basisachtergrond `#EEF7F0`;
- cards en filter-/zoekoppervlakken zijn wit of vrijwel wit en duidelijk leesbaar boven de achtergrond;
- achtergronddecoratie concurreert nooit met tekst of bediening;
- transparantie/blur mag ondersteunend worden gebruikt, maar leesbaarheid en contrast gaan voor.

De eerdere oranje achtergrond is geen actuele visuele referentie meer.

## Meldingen en feedback

Voor passieve applicatiemeldingen geldt één centraal patroon:
- succes-, fout-, waarschuwing-, informatie- en voortgangsmeldingen worden niet midden in het scherm geplaatst;
- zij verschijnen in een vaste onderste balk over de volle schermbreedte;
- de balk heeft dezelfde hoogte als de header: `58px` op grotere schermen en `64px` op mobiel;
- achtergrond is `#008000` en tekst/iconen zijn wit;
- de melding mag een compacte OK- of detailactie bevatten zolang de balkhoogte gelijk blijft;
- technische details mogen op verzoek boven de balk worden uitgeklapt, maar de meldingenbalk zelf verandert niet van hoogte;
- tijdelijke mobiele artikelfeedback volgt hetzelfde patroon.

Interactieve dialogen waarin de gebruiker gegevens moet invoeren of een expliciete keuze moet bevestigen blijven dialogen; zij zijn geen passieve melding en worden niet in de onderste balk gepropt.

## Zoeken, invoer en filters

- zoek- en filtervelden hebben dezelfde visuele familie;
- tekst is `14px`;
- interactieve velden hebben voldoende hoogte en een duidelijk focusbeeld;
- op mobiel is een touchhoogte van minimaal ongeveer `44px` het uitgangspunt;
- veldachtige mobiele rijen houden links en rechts minimaal de centrale `1ch`-marge aan;
- labels zijn duidelijk maar visueel ondergeschikt aan de inhoud;
- filters worden logisch gegroepeerd en blijven leesbaar bij smalle schermen;
- focus gebruikt de donkere brand-ink en mag niet alleen door kleurverschil onzichtbaar subtiel zijn.

## Cards en lijstregels

Een standaard listcard bevat:
- primaire informatie links;
- secundaire metadata/chips onder of naast de primaire tekst;
- status/aantal/chevron aan de rechterkant wanneer relevant;
- één duidelijk klikdoel per rij, bij voorkeur de hele card;
- witte of bijna-witte surface met rustige rand/schaduw;
- consistente padding en afronding.

De primaire itemnaam mag `16px` gebruiken als hoofdnadruk; overige tekst blijft `14px`.

## Badges, chips en aantallen

- badges/chips gebruiken `14px`; zij ogen compacter door padding, achtergrond en gewicht, niet door kleinere tekst;
- aantallen gebruiken eveneens `14px`;
- pill-/chipvormen zijn ondersteunend en mogen niet sterker concurreren dan de primaire schermactie;
- numerieke aantallen mogen tabular numerals gebruiken.

## Knoppen en acties

- primaire knop: `#008000` met witte tekst/iconen;
- knoptekst is `14px` en niet vet (`font-weight: 400`);
- per scherm is bij voorkeur één dominante primaire actie;
- secundaire acties krijgen minder visueel gewicht;
- volledige-breedteknoppen zijn op mobiel passend wanneer één duidelijke vervolgstap centraal staat;
- disabled-, hover-, active- en focusstatus zijn zichtbaar en consistent;
- de primaire actie mag sticky onderaan staan als dit content en meldingenbalk niet blokkeert.

## Tabellen

- zoek- en filterregel staat direct boven de kolomtitels;
- eerste zoekveld heet `Zoek`;
- filters tonen `Filter` zonder extra label erboven wanneer het bestaande tabelpatroon dat gebruikt;
- niet-numerieke kolommen zijn links uitgelijnd;
- numerieke kolommen zijn rechts uitgelijnd;
- checkboxkolommen zijn gecentreerd;
- titel, filter en cellen van één kolom gebruiken exact dezelfde uitlijning;
- Nederlandse decimaalnotatie wordt gebruikt waar van toepassing;
- sortering is beschikbaar waar het tabelcontract dit voorschrijft;
- tabelheaders gebruiken `#008000` met witte tekst en witte sorteer-/resize-indicatoren;
- actieve kolom/focus op lichte surfaces gebruikt de donkere brand-ink;
- horizontale scroll is toegestaan wanneer responsive reductie anders inhoud verbergt;
- hergebruik `Table`/`DataTable` en bestaande resize-/filterpatronen.

## Iconen en toegankelijkheid

- iconen zijn functioneel, eenvoudig en consistent;
- iconen tellen niet mee als één van de twee tekstgroottes wanneer zij als icoon zijn gemarkeerd;
- klikbare iconen hebben een bruikbaar touch-/klikgebied;
- interactieve elementen hebben een zichtbare focusstatus;
- kleur is nooit het enige signaal voor betekenis;
- tekst en iconen op `#008000` zijn wit voor voldoende contrast;
- leesbaarheid en contrast gaan voor decoratieve transparantie.

## Centrale componenten

Nieuwe schermen hergebruiken waar passend bestaande centrale componenten en patronen, waaronder:
- `AppShell`;
- header/branding;
- `AppFeedbackProvider` voor passieve applicatiemeldingen;
- `Card`;
- `Button`;
- inputs/search/selects;
- listcard-/badge-/statuspatronen;
- `Table`/`DataTable`;
- `ResizableHeaderCell`;
- bestaande loading-, empty- en errorstates.

Maak geen lokale variant van een bestaand component alleen om kleine visuele verschillen te realiseren.

## Kernflowconsistentie

Voor de mobiele kernflow **Voorraad → Bijna op → Winkelen → Kassa → Uitpakken** gelden dezelfde:
- typografie;
- merk- en surfacekleuren;
- lichtgroen gevlekte achtergrond waar de kernflow die achtergrond gebruikt;
- spacinglogica en mobiele `1ch`-binnenmarge;
- zoek-/filtertaal;
- card- en statuspatronen;
- primaire-actielogica;
- onderste meldingenbalk;
- focus- en touchregels.

Functionele verschillen tussen deze schermen mogen zichtbaar zijn, maar ze voelen als één applicatie en niet als losse modules.

## Mobiel Voorraad-artikeldetail

Het mobiele detailscherm van een voorraadartikel is een vereenvoudigde presentatie van bestaande Voorraad-functionaliteit en introduceert geen parallel domeinmodel.

Vaste regels:
- het scherm gebruikt hetzelfde huishoudartikel en dezelfde voorraad-/historie-/settings-API's als het bestaande desktop-detailscherm;
- de actuele voorraad staat bovenaan met een directe `−`- en `+`-bediening;
- `−` verlaagt de voorraad met één via de bestaande afboek-/inventory-eventlogica;
- `+` verhoogt de voorraad met één via de bestaande handmatige voorraadcorrectie;
- aparte snelle acties **Voorraad aanpassen** en **Afboeken** worden niet getoond;
- de rij **Locatie** wordt alleen getoond wanneer **Waar Inhuis** actief is (`location_tracking_level != none`);
- bij meerdere actieve voorraadlocaties bepaalt de geselecteerde locatie op welke voorraadrij `+` en `−` werken;
- detail- en actierijen houden altijd de centrale `1ch`-binnenmarge aan, ook bij browserzoom of responsive emulatie;
- het detailscherm heeft geen vaste algemene `Opslaan`-knop; een specifieke instelling wordt direct/expliciet opgeslagen vanuit zijn eigen interactie;
- de gebruikerszichtbare term voor de shoppingmodule blijft **Winkelen**.

De sectie **Snelle acties** bevat precies:
1. **Voorkeurswinkel** — toont/bewerkt de bestaande huishoudinstelling `favorite_store`;
2. **Aankoophistorie** — toont uitsluitend aankoopgebeurtenissen van het huidige huishoudartikel;
3. **Naar inkooplijstje** — voegt het huidige huishoudartikel direct toe aan de actieve lijst in **Winkelen**, opent geen extra detailscherm en geeft feedback via de onderste meldingenbalk.

Niet opnemen als nieuwe mobiele functionaliteit:
- `Naar boodschappen`;
- `Verbruik registreren`;
- een los verwijder-/archiveerpatroon dat niet al functioneel is overeengekomen;
- een generieke Opslaan-knop voor het gehele detailscherm.

## Wijzigings- en governance-regel

Deze styleguide is onderdeel van de repository-governance.

Voor iedere PR met gebruikerszichtbare frontendwijzigingen wordt de styleguide-impact expliciet beoordeeld.

### Styleguide-dragende wijziging

Wijzigingen aan onder meer:
- `frontend/src/ui/**`;
- frontend stylingbestanden (`.css`, `.scss`, `.sass`, `.less`);
- Inhuis visuele assets onder `frontend/public/inhuis-*`;

moeten in dezelfde PR:
1. `docs/project/UI-STYLEGUIDE-SUMMARY.md` bijwerken;
2. in de PR-body opnemen:
   - `STYLEGUIDE_IMPACT: updated`
   - `STYLEGUIDE_REASON: <concrete toelichting>`

Een marker alleen mag een verplichte styleguide-update niet omzeilen.

### Overige UI-wijziging

Een overige frontend UI-/schermwijziging moet óf de styleguide bijwerken, óf expliciet verklaren waarom de bestaande regels ongewijzigd blijven:
- `STYLEGUIDE_IMPACT: reviewed-no-change`
- `STYLEGUIDE_REASON: <concrete toelichting>`

### Niet-UI-wijziging

Voor een wijziging zonder UI-impact mag worden gebruikt:
- `STYLEGUIDE_IMPACT: not-applicable`

De CI-gate `UI styleguide governance validation` controleert fail-closed:
- documentstructuur;
- synchronisatie tussen de centrale design tokens en dit document;
- gewijzigde UI-paden ten opzichte van de PR-base;
- verplichte styleguide-update voor styleguide-dragende wijzigingen;
- expliciete reviewverklaring voor overige UI-wijzigingen.

## Historische styleguidedocumenten

`docs/Rezzerv-Styleguide_v05.08.md` en `Rezzerv-Styleguide_v05.14.md` blijven behouden als audittrail van eerdere PO-besluiten. Hun actuele regels zijn hierboven geconsolideerd. Nieuwe wijzigingen worden niet als nieuwe losse styleguideversies toegevoegd tenzij de PO daar expliciet om vraagt; de canonieke bron wordt direct bijgewerkt.