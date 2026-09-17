# Inhuis UI-styleguide

Status: **canonieke UI-bron** voor gebruikerszichtbare vormgeving en interactiepatronen in Inhuis.  
Laatst inhoudelijk vastgesteld door de PO: 16 september 2026.

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
- bestaande lokale `font-size`-waarden die door `frontend/src/ui/typography.css` naar 14/16 px worden genormaliseerd zijn geen precedent voor nieuwe code;
- nieuwe UI-code introduceert geen derde gebruikerszichtbare tekstmaat.

## Kleuren

Centrale tokens:
- `--color-brand-primary`: `#1A3E2B`
- `--color-brand-light`: `#D9F5E0`
- `--color-text-primary`: `#1A1A1A`
- `--color-text-inverse`: `#FFFFFF`
- `--color-border-default`: `#CFE8D6`
- `--color-table-grid`: `#8FD19E`

Gebruik:
- donkergroen is de primaire Inhuis-merkkleur voor header, primaire acties, focus/accent en geselecteerde status;
- normale tekst gebruikt de primaire donkere tekstkleur;
- tekst op donkergroen gebruikt wit;
- lichte groentinten zijn ondersteunend en concurreren niet met de primaire actie;
- voeg geen nieuwe dominante merkkleur toe zonder expliciete PO-beslissing en styleguide-update;
- fout-, waarschuwing- en succeskleuren mogen semantisch afwijken, maar worden niet als alternatieve merkkleur ingezet.

## Spacing, radius en elevation

Centrale spacingtokens:
- `--space-xs`: `4px`
- `--space-sm`: `8px`
- `--space-md`: `16px`
- `--space-lg`: `24px`
- `--space-xl`: `32px`

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
- bestaande schermspecifieke waarden worden niet automatisch als nieuwe token beschouwd;
- als een bestaande afwijking wordt aangeraakt, wordt bewust gekozen: behouden als expliciete uitzondering of convergeren naar een centraal token.

## Schermopbouw

Voor mobiele kernschermen is de standaardvolgorde:

1. header;
2. zoeken/filteren/context;
3. hoofdinhoud in cards/lijst/tabel;
4. één dominante primaire actie waar nodig.

Alle onderdelen volgen één horizontale uitlijning en herhaalbare spacing. Een scherm introduceert geen eigen navigatie- of actiepatroon wanneer een bestaand centraal patroon beschikbaar is.

## Header en branding

- standaard headerhoogte: `56px`;
- achtergrond: `--color-brand-primary`;
- schermtitel links, in wit;
- gebruikerszichtbaar merk is **Inhuis**;
- het witte Inhuis-logo staat rechts en blijft volledig binnen de header;
- titel en logo zijn verticaal gecentreerd;
- interne technische naamgeving `Rezzerv` mag in code blijven maar wordt niet als gebruikersmerk getoond.

## Mobiele achtergrond en surfaces

De huidige mobiele Voorraad-weergave is de visuele referentie voor de kernflow:
- zachte, warme achtergrond;
- asset `/inhuis-orange-wallpaper.svg`;
- basisachtergrond `#f5e7db`;
- cards en filter-/zoekoppervlakken zijn wit of vrijwel wit en duidelijk leesbaar boven de achtergrond;
- achtergronddecoratie blijft laag in contrast en concurreert nooit met tekst of bediening;
- transparantie/blur mag ondersteunend worden gebruikt, maar leesbaarheid en contrast gaan voor.

Deze achtergrond is een kernflowreferentie, geen verplicht decor voor ieder beheer- of desktop-scherm.

## Zoeken, invoer en filters

- zoek- en filtervelden hebben dezelfde visuele familie;
- tekst is `14px`;
- interactieve velden hebben voldoende hoogte en een duidelijk focusbeeld;
- op mobiel is een touchhoogte van minimaal ongeveer `44px` het uitgangspunt;
- labels zijn duidelijk maar visueel ondergeschikt aan de inhoud;
- filters worden logisch gegroepeerd en blijven leesbaar bij smalle schermen;
- focus gebruikt de primaire merkkleur en mag niet alleen door kleurverschil onzichtbaar subtiel zijn.

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
- numerieke aantallen mogen tabular numerals gebruiken voor rust en uitlijning.

## Knoppen en acties

- primaire knop: donkergroen met witte tekst;
- knoptekst is `14px` en niet vet (`font-weight: 400`);
- per scherm is bij voorkeur één dominante primaire actie;
- secundaire acties krijgen minder visueel gewicht;
- volledige-breedteknoppen zijn op mobiel passend wanneer één duidelijke vervolgstap centraal staat;
- disabled-, hover-, active- en focusstatus zijn zichtbaar en consistent;
- de primaire actie mag sticky onderaan staan als dit de kernflow ondersteunt zonder content te blokkeren.

## Tabellen

- zoek- en filterregel staat direct boven de kolomtitels;
- eerste zoekveld heet `Zoek`;
- filters tonen `Filter` zonder extra label erboven wanneer het bestaande tabelpatroon dat gebruikt;
- niet-numerieke kolommen zijn links uitgelijnd;
- numerieke kolommen zijn rechts uitgelijnd;
- checkboxkolommen zijn gecentreerd;
- titel, filter en cellen van één kolom gebruiken exact dezelfde uitlijning;
- Nederlandse decimaalnotatie wordt gebruikt waar van toepassing;
- lege cellen zijn visueel ondergeschikt;
- sortering is beschikbaar waar het tabelcontract dit voorschrijft;
- actieve kolom gebruikt donkergroen;
- horizontale scroll is toegestaan wanneer responsive reductie anders inhoud verbergt;
- hergebruik `Table`/`DataTable` en bestaande resize-/filterpatronen in plaats van schermspecifieke tabellen.

## Iconen en toegankelijkheid

- iconen zijn functioneel, eenvoudig en consistent;
- iconen tellen niet mee als één van de twee tekstgroottes wanneer zij decoratief/semantisch als icoon zijn gemarkeerd;
- klikbare iconen hebben een bruikbaar touch-/klikgebied, onafhankelijk van hun getekende formaat;
- interactieve elementen hebben een zichtbare focusstatus;
- kleur is nooit het enige signaal voor betekenis;
- leesbaarheid en contrast gaan voor decoratieve transparantie.

## Centrale componenten

Nieuwe schermen hergebruiken waar passend bestaande centrale componenten en patronen, waaronder:
- `AppShell`;
- header/branding;
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
- spacinglogica;
- zoek-/filtertaal;
- card- en statuspatronen;
- primaire-actielogica;
- focus- en touchregels.

Functionele verschillen tussen deze schermen mogen zichtbaar zijn, maar ze voelen als één applicatie en niet als losse modules.

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

`docs/Rezzerv-Styleguide_v05.08.md` en `Rezzerv-Styleguide_v05.14.md` blijven behouden als audittrail van eerdere PO-besluiten. Hun actuele regels zijn hierboven geconsolideerd. Nieuwe wijzigingen worden niet als nieuwe losse styleguideversies toegevoegd tenzij de PO daar expliciet om vraagt; de canonieke bron wordt voortaan direct bijgewerkt.
