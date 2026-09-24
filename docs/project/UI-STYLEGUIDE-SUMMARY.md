# Inhuis UI-styleguide

Status: **canonieke UI-bron** voor gebruikerszichtbare vormgeving en interactiepatronen in Inhuis.  
Laatst inhoudelijk vastgesteld door de PO: 24 september 2026.

Deze styleguide is de actuele leesbare UI-bron voor nieuwe schermen en wijzigingen aan bestaande schermen. Historische styleguidedocumenten blijven audittrail, maar nieuwe UI-beslissingen worden hier geconsolideerd. Bij een conflict met een oudere UI-notitie geldt deze canonieke styleguide, tenzij de PO expliciet een nieuwere afwijking heeft vastgesteld.

De mobiele Voorraadbaseline is op **22 september 2026** ingezet en op **23 september 2026** door de PO verder verfijnd. De actuele variant combineert de rustige vlakke lijststructuur met de lichtgroene gevlekte Inhuis-achtergrond, een mobiele header via de centrale primaire kleurtoken (standaard `#005F6A`) en een gebruikersspecifieke onderste actiebalk. Eerdere Voorraad-borging geldt niet meer wanneer zij met dit nieuwere PO-besluit conflicteert.

Het mobiele **Voorraad-artikeldetail** is op **23 september 2026** naar dezelfde nieuwe mobiele richting gemigreerd. Het hoofdscherm Voorraad blijft de primaire lijstbaseline; het artikeldetail is de actuele detailbaseline voor gedeelde navigatie, kleur en artikelpresentatie.

Historische besluiten die hierin zijn opgenomen:
- `docs/Rezzerv-Styleguide_v05.08.md`: knoptekst is niet vet;
- `Rezzerv-Styleguide_v05.14.md`: niet-numerieke tabelkolommen links, numerieke kolommen rechts, met gelijke uitlijning voor titel/filter/cellen.

## Mobiele ontwerpbaseline vanaf 22 september 2026

Voor mobiele modulehoofschermen geldt, te beginnen met **Voorraad**, de visuele grammatica uit het door de PO aangeleverde ontwerpvoorstel:

- een rustige **lichtgroene gevlekte Inhuis-achtergrond** via de bestaande groene wallpaper; blur en zwevende glassmorphism-cards blijven vervallen;
- ieder beveiligd mobiel scherm krijgt vanuit de centrale `MobileAppChrome` linksboven de gedeelde knop **Terug** via `--color-mobile-ui-primary` (standaard `#005F6A`); een aanwezige module-/appheader reserveert hiervoor links ruimte en toont daarnaast de schermtitel en waar van toepassing het **witte Inhuis-logo**;
- één applicatiebrede primaire donkergroene/blauwgroene tokenfamilie met standaardkleur **`#005F6A`** voor headers, primaire knoppen, tabelheaders, voorraadmutatieknoppen, focusaccenten en actieve mobiele accenten; er wordt geen tweede primaire donkergroene tint gebruikt;
- zoeken en filters staan compact boven de inhoud, zonder een grote omhullende filtercard;
- de voorraadlijst vormt één rustige witte lijstgroep met subtiele scheidingslijnen; iedere rij toont productfoto, artikelnaam, ondersteunende metadata, hoeveelheid en chevron;
- geen losse verhoogde card per voorraadartikel en geen decoratieve schaduwen als hoofdstructuur;
- een vaste witte onderste actiebalk met maximaal vier door de **huidige gebruiker recent gebruikte en nog beschikbare acties**, waarbij de **actief geopende module altijd wordt uitgesloten**, aangevuld met beschikbare andere acties wanneer nog onvoldoende gebruikshistorie bestaat, plus altijd **Meer** als laatste item;
- de bestaande actie **Incidentele aankoop** blijft functioneel beschikbaar, maar staat als compacte groene actie bij de lijstcontext en is niet langer een grote sticky knop boven een apart inline meldingenblok;
- alle bestaande data-, autorisatie-, huishoudisolatie-, detailroute- en filterfunctionaliteit blijft leidend. Dit PO-besluit wijzigt de presentatie, niet het domeinmodel.

Andere mobiele kernschermen worden niet stilzwijgend meegewijzigd. Totdat zij expliciet worden gemigreerd mogen zij tijdelijk nog de eerdere visuele shell gebruiken. Nieuwe of aangepaste tests borgen de actuele groene wallpaper, maar mogen blur, individuele zwevende schaduwcards of de oude sticky CTA niet opnieuw afdwingen.

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
- veldlabels, de geselecteerde waarde van een dropdown en de opties in de geopende dropdownlijst gebruiken dezelfde `14px` bodymaat; een dropdown introduceert geen grotere tekstmaat;
- `16px` is voor schermtitels, sectietitels en expliciete hoofdnadruk;
- extra hiërarchie komt uit gewicht, kleur en witruimte, niet uit een derde tekstgrootte;
- knoptekst gebruikt normaal gewicht (`font-weight: 400`) en is niet vet;
- titels/hoofdnadruk mogen semibold/bold zijn wanneer dat voor hiërarchie nodig is;
- decoratieve iconen en symbolen zijn geen tekst en mogen onafhankelijk worden geschaald;
- nieuwe UI-code introduceert geen derde gebruikerszichtbare tekstmaat;
- de twee mobiele referentieschermen worden beoordeeld op de **uiteindelijk gerenderde** typografie: centrale normalisatie naar `14px`/`16px` is leidend boven historische lokale CSS-declaraties met andere maten.

## Kleuren

Centrale tokens:
- `--color-brand-primary`: `#005F6A` — centrale brand-/interactiekleur;
- `--color-ui-primary`: `#005F6A` — dezelfde centrale primaire UI-kleur voor desktop, tabellen en gedeelde componenten;
- `--color-mobile-ui-primary`: `#005F6A` — dezelfde centrale primaire UI-kleur voor mobiele headers, acties, steppers, focusaccenten en passieve feedbackoverlays;
- deze drie tokens mogen niet naar verschillende donkergroene/blauwgroene hexwaarden divergeren; de standaardwaarde is `#005F6A`.
- **Instellingen → Weergave** mag op het huidige apparaat één afwijkende donkere hoofdkleur kiezen; die runtimevoorkeur overschrijft alle drie primary-tokens tegelijk en wordt lokaal in de browser bewaard. **Standaard herstellen** zet alle drie terug op `#005F6A`.
- de instelbare hoofdkleur moet met witte tekst minimaal WCAG-contrast 4,5:1 behouden; te lichte kleuren worden geweigerd.
- `--color-ui-primary-text`: `#FFFFFF` — witte tekst en iconen op primaire blauw-groene surfaces;
- `--color-brand-light`: `#D9F5E0`;
- `--color-text-primary`: `#1A1A1A`;
- `--color-text-inverse`: `#FFFFFF`;
- `--color-border-default`: `#CFE8D6`;
- `--color-table-grid`: `#8FD19E`.

Gebruik:
- `#005F6A` is de standaard primaire Inhuis-UI-kleur; alle primaire surfaces lezen de centrale tokens zodat een geldige lokale Weergave-voorkeur applicatiebreed tegelijk doorwerkt;
- tekst en iconen op `#005F6A` gebruiken centraal `#FFFFFF`; dit geldt applicatiebreed voor primaire gekleurde surfaces en vervangt de eerdere donkere tekstkleur;
- `#005F6A` blijft de brand-ink voor tekst, iconen, focus/accent en geselecteerde status op lichte of witte surfaces;
- normale tekst gebruikt de primaire donkere tekstkleur;
- lichte groentinten zijn ondersteunend en concurreren niet met de primaire actie;
- de legacy-tokens `--rz-accent` en `--rz-green-dark` worden centraal gekoppeld aan `--color-ui-primary`; zij definiëren nooit een eigen donkergroene waarde;
- voeg geen nieuwe dominante merkkleur toe zonder expliciete PO-beslissing en styleguide-update;
- witte tekst op gekleurde primaire surfaces blijft verplicht; dit geldt zowel op `#005F6A` als op de mobiele Voorraadpilottint `#005F6A`;
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

Voor mobiele modulehoofschermen is de standaardvolgorde:
1. compacte moduleheader;
2. zoeken/filteren/context;
3. hoofdinhoud in lijst/cards/tabel;
4. één dominante primaire actie waar nodig;
5. vaste `MobileRecentActionsBar` onderin op ieder beveiligd mobiel scherm.

Alle onderdelen volgen één horizontale uitlijning en herhaalbare spacing. De vaste onderste navigatie is onderdeel van de centrale mobiele applicatieshell en wordt niet meer per scherm geïmplementeerd.

Voor de mobiele Voorraadpilot geldt:
- de hoofdinhoud staat gecentreerd en wordt niet breder dan circa `640px`;
- op smalle mobiele breedtes is circa `10px` horizontale buitenruimte de referentie; op ruimere mobiele breedtes circa `14px`;
- de lijst gebruikt subtiele scheidingslijnen in één surface in plaats van verticale ruimte tussen losse cards;
- de scherminhoud reserveert onderaan voldoende ruimte voor de vaste onderste navigatie plus `env(safe-area-inset-bottom)`.

## Passieve meldingen op mobiel

Passieve succes-, info-, waarschuwing- en foutmeldingen gebruiken uitsluitend de centrale `AppFeedbackProvider/useAppFeedback` en worden op mobiele schermen als **overlay** gerenderd:
- de melding neemt geen ruimte in de documentflow in en schuift onderliggende inhoud nooit op;
- de mobiele overlay gebruikt `--color-mobile-ui-primary` (standaard `#005F6A`);
- één klik/tap **op de melding** sluit de melding;
- één klik/tap **elders op het scherm** sluit de melding;
- zonder gebruikersactie verdwijnt een passieve melding automatisch na **maximaal 3.000 ms**;
- een scherm maakt hiervoor geen lokale inline succes-/foutmelding of eigen timer;
- interactieve bevestigingen, formulieren, technische-detaildialogen en voortgangsfeedback zijn niet transient en verdwijnen niet automatisch; zij blijven de bestaande AppFeedback-dialogsemantiek volgen.

Op ieder beveiligd mobiel scherm staat de feedbackoverlay boven de vaste `MobileRecentActionsBar`, zodat melding en navigatie elkaar niet afdekken.

## Mobiele navigatie

Inhuis gebruikt op mobiel twee navigatieniveaus:
- hoofdmodules worden rechtstreeks geopend vanuit de centrale hoofd-/tabnavigatie;
- details en vervolgstappen liggen op een navigatiestack boven de module waaruit zij zijn geopend.

Voor de browserapp geldt:
- de browsergeschiedenis blijft de inhoudelijke bron voor terugnavigatie;
- elk beveiligd mobiel scherm toont linksboven de gedeelde knop **Terug** vanuit `MobileAppChrome`; alleen het centrale `MobileBackControl` mag `navigate(-1)` gebruiken en valt zonder bruikbare geschiedenis veilig terug op `/home`;
- schermspecifieke terugknoppen of hard gecodeerde terugroutes zijn niet toegestaan;
- een detailroute wordt normaal via routing geopend;
- terugkeren naar een lijst hoort zoek-/filter-/sorteringscontext en scrollpositie zo veel mogelijk te behouden.

Voor een native mobiele shell geldt hetzelfde route-/stackmodel, maar zonder zichtbare browserbediening:
- terugpijl, iOS edge-swipe en Android systeem-back voeren semantisch dezelfde stap terug uit;
- terug betekent terug naar de herkomstcontext en niet naar een hard gecodeerde hoofdmodule;
- een sprong naar een hoofdmodule is een modulewissel en geen terugactie.

## Header en branding

De bestaande generieke/desktopheader blijft:
- standaard `58px` hoog op grotere schermen;
- `--color-ui-primary` (standaard `#005F6A`) met witte titel/iconen;
- gebruikerszichtbaar merk **Inhuis**; interne technische naamgeving `Rezzerv` wordt niet als gebruikersmerk getoond.

Voor de mobiele Voorraadbaseline geldt:
- compacte gekleurde header via `--color-mobile-ui-primary` (standaard `#005F6A`);
- schermtitel **Voorraad** links;
- wit Inhuis-logo rechts;
- geen desktopachtige huishoudenregel of userbox in de module-root;
- de browser-/native shell en onderste actiebalk leveren de overige appcontext;
- detail- en nog niet gemigreerde schermen mogen tijdelijk de bestaande header houden totdat zij expliciet worden omgezet.

## Mobiele achtergrond en surfaces

Voor de mobiele Voorraadbaseline:
- pagina-achtergrond gebruikt de bestaande lichtgroene gevlekte `/inhuis-green-wallpaper.svg` op een lichte groene basis;
- de oranje wallpaper is geen Voorraadbaseline;
- blur/glassmorphism is niet toegestaan als hoofdstructuur;
- zoeken en filters staan compact op de pagina zonder verhoogde omhullende card;
- voorraadartikelen staan in één witte lijstsurface met subtiele scheidingslijnen;
- individuele voorraadregels hebben geen decoratieve elevation of zwevende-cardpresentatie;
- focus-, hover- en active-status blijven duidelijk zichtbaar.

Het nog niet gemigreerde **Voorraad-artikeldetail** mag tijdelijk de oudere groen gevlekte surface behouden; die tijdelijke detailstijl is geen precedent voor nieuwe modulehoofschermen.

## Mobiele referentieschermen

### Referentie A — mobiele lijstweergave: Voorraad

**Voorraad** is vanaf 22 september 2026 de concrete visuele referentie voor nieuwe mobiele module-/lijstschermen.

Vaste kenmerken:
- compacte gekleurde header met **Voorraad links** en het witte Inhuis-logo rechts;
- zoekveld als eerste ingang, gevolgd door compacte locatie-/artikelgroep-/sorteerfilters; artikelsortering biedt **Naam A–Z** en **Naam Z–A**, terwijl sortering op aantal niet wordt aangeboden;
- iedere voorraadregel toont voor bevoegde Admin/Eigenaar direct `−` vóór en `+` na het aantal; `−` boekt exact één eenheid af via de bestaande inventory-eventlogica en `+` verhoogt exact één eenheid via de bestaande handmatige voorraadcorrectie; na iedere mutatie wordt de backendvoorraad opnieuw geladen;
- interactieve zoek-/select-/actievelden hebben minimaal circa `44px` touchhoogte;
- aantalscontext en de bestaande actie **Incidentele aankoop** staan compact boven de lijst;
- één witte lijstcontainer met subtiele horizontale scheidingen;
- iedere rij toont waar beschikbaar een representatieve productfoto, artikelnaam, ondersteunende metadata, hoeveelheid en chevron;
- de hele rij is het detailklikdoel;
- geen afzonderlijke schaduwcard, wallpaper, blur of sticky schermbrede CTA per artikel;
- vaste witte onderste actiebalk met maximaal vier recent gebruikte, voor de huidige gebruiker nog beschikbare acties en altijd **Meer** als laatste item; de actieve module zelf wordt bewust niet in die balk getoond;
- onderaan wordt altijd ruimte gereserveerd voor de navigatie en safe-area.

### Referentie B — mobiel detailscherm: Voorraad-artikeldetail (tijdelijk legacy-visueel)

Het bestaande Voorraad-artikeldetail blijft voorlopig functioneel en visueel ongewijzigd. De bestaande plus/min-, locatie-, instellingen- en snelle-actiescontracten blijven geldig, maar de oudere wallpaper/card-shell is **niet** meer de visuele bron voor nieuwe mobiele schermen.

Bij latere migratie van het detailscherm wordt de presentatie naar Referentie A en het PO-ontwerpdocument gebracht zonder het domeinmodel, API's of voorraadmutaties te wijzigen.

### Typografie, touch en routes

Voor de nieuwe Voorraadbaseline blijven de generieke toegankelijkheidscontracten van kracht:
- uiteindelijk gerenderde tekst gebruikt `14px` body en `16px` titel/hoofdnadruk;
- interactieve primaire touchdoelen zijn minimaal circa `44px` hoog;
- productthumbnail blijft waar beschikbaar circa `52 × 52px`;
- alleen bestaande geautoriseerde routes worden in de onderste navigatie opgenomen; een ontwerpitem zonder werkende appfunctie wordt niet als dode navigatie nagebouwd.

## Meldingen en feedback

De centrale authority voor feedback is `AppFeedbackProvider/useAppFeedback`. Schermen maken geen eigen tijdelijke succes-, info-, waarschuwing- of foutbalk wanneer deze centrale component het patroon afdekt.

### Mobiele passieve feedback

Op mobiele schermen is passieve feedback altijd een **overlay**:
- de melding staat buiten de documentflow en schuift inhoud nooit omlaag of omhoog;
- er wordt op mobiel geen permanente lege feedbackbalk of extra feedback-clearance gereserveerd;
- de overlay gebruikt `--color-mobile-ui-primary` (standaard `#005F6A`) met witte tekst;
- tik/klik **op de melding** sluit haar direct;
- tik/klik **elders op het scherm** sluit haar direct;
- zonder interactie verdwijnt de melding automatisch na maximaal **3.000 ms**;
- een scherm implementeert hiervoor geen eigen timer, lokale feedbackstate of lokale feedback-CSS;
- op schermen met een vaste onderste actiebalk staat de overlay daar visueel boven.

Interactieve bevestigingen, invoerformulieren, technische-detaildialogen en voortgangsmeldingen zijn niet transient. Zij blijven centrale AppFeedback-dialogen en verdwijnen niet automatisch.

### Desktop en nog niet gemigreerde niet-mobiele feedback

Op desktop mag het bestaande centrale onderste-balkpatroon blijven gelden:
- de feedbacklaag is fixed en verschuift de pagina-inhoud niet;
- achtergrond gebruikt `--color-ui-primary` (standaard `#005F6A`) met witte tekst/iconen;
- interactieve dialogen blijven afzonderlijke dialogen en worden niet in de balk gepropt.

## Zoeken, invoer en filters

- zoek- en filtervelden hebben dezelfde visuele familie;
- tekst is `14px`;
- gebruikerszichtbare dropdowns gebruiken de centrale Inhuis-`Select`-component; native browser/OS-`<select>`-popups zijn voor deze schermen niet toegestaan omdat hun geopende optielijst de Inhuis-typografie niet betrouwbaar volgt;
- de centrale Inhuis-`Select` gebruikt voor veldwaarde én alle opties in de geopende lijst exact `14px`, gelijk aan de veldlabels;
- de geopende Inhuis-`Select` wordt als overlay op de centrale applicatielaag gerenderd en ligt altijd vóór de onderliggende cards, lijsten en tabellen; stacking contexts van de inhoud mogen de dropdown niet afdekken;
- bij **zoekgestuurde kandidaatselectie** worden gevonden kandidaten direct onder het zoekveld zichtbaar; de gebruiker hoeft niet eerst een gesloten resultaatveld of dropdown te openen;
- zo'n zoekkandidatenlijst toont maximaal **5 kandidaten** tegelijk en gebruikt de centrale `SearchCandidateList`/`searchCandidatePolicy`; dit geldt applicatiebreed, waaronder Boodschappenlijst, Voorraad-autocomplete, handmatige externe productzoeking en Catalogus/GPC-zoeking;
- automatische GS1 GPC-classificatie toont bij een nog ongeclassificeerd Catalogusartikel maximaal **5 direct zichtbare kandidaten**, gerangschikt op indicatieve matchsterkte; iedere kandidaat toont minimaal Brickcode, omschrijving, hiërarchie en een korte reden voor de match, en kan afzonderlijk worden bevestigd of genegeerd;
- ieder actief Inhuis-productintent declareert centraal een GPC-kandidaatstrategie: generieke taxonomierangschikking, expliciete semantische GPC-termen of aantoonbaar `manual_only` met reden; CI blokkeert nieuwe taxonomie-items zonder zo'n strategie;
- wanneer Nederlandse bon-/productterminologie onvoldoende rechtstreeks overeenkomt met de officiële Engelstalige GS1 GPC-termen, worden semantische brugtermen centraal in de producttaxonomie vastgelegd; schermcode bevat hiervoor geen artikel-specifieke uitzonderingen;
- wanneer automatische GS1 GPC-classificatie in **Externe databases** ontbreekt of niet eenduidig is, mag de gebruiker handmatig zoeken op Brickcode of producttype; alleen resultaten uit de officiële geïmporteerde `gpc_bricks`-catalogus zijn selecteerbaar, maximaal 5 tegelijk;
- een handmatig gekozen GPC Brick is geen vrije tekstwaarde: de backend valideert de Brick opnieuw tegen de officiële GPC-catalogus en bewaart de classificatieherkomst als `manual`; automatisch overgenomen classificaties bewaren herkomst `external`;
- gewone tabel-/kolomfilters, locatiekeuzes en andere statische keuzelijsten zijn geen zoekkandidatenlijst en vallen niet onder deze maximum-5-regel;
- interactieve velden hebben voldoende hoogte en een duidelijk focusbeeld;
- op mobiel is een touchhoogte van minimaal ongeveer `44px` het uitgangspunt;
- veldachtige mobiele rijen houden links en rechts minimaal de centrale `1ch`-marge aan;
- labels zijn duidelijk maar visueel ondergeschikt aan de inhoud;
- filters worden logisch gegroepeerd en blijven leesbaar bij smalle schermen;
- focus gebruikt de donkere brand-ink en mag niet alleen door kleurverschil onzichtbaar subtiel zijn.

## Cards en lijstregels

Een standaard listcard op niet-gemigreerde schermen bevat:
- primaire informatie links;
- secundaire metadata/chips onder of naast de primaire tekst;
- status/aantal/chevron aan de rechterkant wanneer relevant;
- één duidelijk klikdoel per rij, bij voorkeur de hele card;
- witte of bijna-witte surface met rustige rand/schaduw;
- consistente padding en afronding.

De primaire itemnaam mag `16px` gebruiken als hoofdnadruk; overige tekst blijft `14px`. De mobiele Voorraadpilot gebruikt in plaats van losse listcards één vlakke lijstsurface met gescheiden rijen.

## Productafbeeldingen

- productafbeeldingen uit externe productbronnen worden als ondersteunende productidentificatie getoond en vervangen nooit de artikelnaam of GTIN;
- Cataloguslijsten gebruiken waar beschikbaar een compacte thumbnail naast de artikelnaam, zonder een extra brede fotokolom af te dwingen;
- Catalogusdetail mag dezelfde afbeelding groter tonen met behoud van beeldverhouding en `object-fit: contain`;
- wanneer een gebruiker `platform.catalog.update` heeft, is het volledige Catalogusdetail-fotovlak het klikdoel voor **Foto uploaden** of **Foto maken**; de keuze wordt via de centrale AppFeedback-dialog aangeboden en de fotozone houdt een duidelijke focusstatus;
- een door de gebruiker gekozen Catalogusfoto wordt vóór opslag client-side verkleind tot maximaal **640 × 640px** met behoud van beeldverhouding en gecomprimeerd naar JPEG; het detailvlak blijft circa **160 × 160px** en gebruikt `object-fit: contain`, zodat beeldkwaliteit en opslagomvang in balans blijven;
- **Foto maken** gebruikt een live camerastream via de browser-API `navigator.mediaDevices.getUserMedia()` en opent dus geen bestandskiezer; op mobiele toestellen wordt waar mogelijk de achtercamera gevraagd via `facingMode: environment`, terwijl desktop/laptop de beschikbare webcam gebruikt;
- de camerastream wordt in een Inhuis-dialog als live preview getoond met expliciete acties **Foto maken** en **Annuleren**; bij sluiten, navigeren of na het maken van de foto worden alle cameratracks direct gestopt;
- als cameratoegang ontbreekt, geweigerd wordt of de camera al bezet is, krijgt de gebruiker een begrijpelijke foutmelding; **Foto uploaden** blijft de afzonderlijke bestandskiezerroute;
- **Voorraad**, **Bijna op** en **Boodschappenlijst/Winkelen** tonen een stabiele **representatieve foto op huishoudartikelniveau** als compacte thumbnail direct naast de artikelnaam;
- winkel- en GTIN-specifieke productnummers mogen wisselen zonder dat de Voorraadfoto mee hoeft te wisselen: de gekozen representatieve foto wordt persistent op het huishoudartikel bewaard;
- de GS1 GPC Brick vormt de compatibiliteitsgrens voor automatische fotokeuze: een exacte Catalogusfoto mag als representatieve foto worden gebruikt wanneer het product dezelfde Brick heeft als het huishoudartikel; wanneer het huishoudartikel nog geen Brick-relatie heeft, mag een artikelgroep alleen een Brick leveren als de groepsnaam exact en eenduidig overeenkomt met de officiële Brickomschrijving of Nederlandse Brickvertaling;
- bij bestaande data wordt de representatieve foto terugwerkend gevuld uit, in volgorde, een reeds gekoppeld exact Catalogusproduct, een recent exact aankoopproduct met passende Brick, of een exact actief Catalogusproduct met foto binnen dezelfde Brick;
- een eenmaal gekozen representatieve foto blijft stabiel bij latere aankopen bij andere winkels en wordt niet automatisch door een andere winkelverpakking vervangen;
- operationele schermen voeren geen eigen externe afbeeldingszoekactie uit; de bronafbeelding komt uit de persistente Catalogus-`image_url`, waarna de geselecteerde afbeelding op huishoudartikelniveau wordt vastgelegd;
- oudere huishoudartikelen zonder representatieve foto mogen daarnaast nog terugvallen op bestaande canonieke `product_identities`, exacte GTIN/barcode of bevestigde externe artikelkoppeling; vrije naamgelijkheid alleen blijft onvoldoende;
- de standaard operationele thumbnail is circa **52 × 52px**, gebruikt `object-fit: contain` en mag op mobiel als vaste eerste contentkolom vóór de artikeltekst staan;
- ontbrekende of niet-laadbare afbeeldingen krijgen een rustige neutrale beeld-placeholder zonder broken-image-icoon; de artikelnaam blijft altijd zichtbaar;
- bij Boodschappenlijst/Winkelen wordt alleen een Catalogusfoto geprojecteerd als de regel canoniek naar een huishoudartikel en daarmee naar een Catalogusproduct verwijst; producttype- of artikelgroepregels krijgen niet kunstmatig een willekeurige productfoto;
- een externe afbeelding-URL wordt niet automatisch gebruikt om een reeds aanwezige Catalogusafbeelding te overschrijven.

## Badges, chips en aantallen

- badges/chips gebruiken `14px`; zij ogen compacter door padding, achtergrond en gewicht, niet door kleinere tekst;
- aantallen gebruiken eveneens `14px`;
- pill-/chipvormen zijn ondersteunend en mogen niet sterker concurreren dan de primaire schermactie;
- numerieke aantallen mogen tabular numerals gebruiken.

## Knoppen en acties

- primaire knop gebruikt `--color-ui-primary` met witte tekst/iconen (`#FFFFFF`); standaard is dat `#005F6A`, en een geldige Weergave-voorkeur overschrijft de primaire tokenfamilie als één geheel;
- knoptekst is `14px` en niet vet (`font-weight: 400`);
- per scherm is bij voorkeur één dominante primaire actie;
- secundaire acties krijgen minder visueel gewicht;
- volledige-breedteknoppen zijn op mobiel passend wanneer één duidelijke vervolgstap centraal staat;
- disabled-, hover-, active- en focusstatus zijn zichtbaar en consistent;
- de primaire actie mag sticky onderaan staan als dit content en de tijdelijke feedbackoverlay niet blokkeert;
- een sticky mobiele actie krijgt expliciet voldoende bottom-offset boven eventuele tijdelijke feedbackoverlay en de scrollcontainer reserveert daarnaast voldoende eindruimte om de actie volledig zichtbaar en bereikbaar te maken.

## Tabellen

De standaard desktop-/matrixweergave toont waar een tabel pagineert **10 zichtbare bodyregels** per pagina. Wanneer minder dan 10 records beschikbaar zijn, mag de tabelhoogte met lege niet-interactieve fillerregels op 10 regels worden gestabiliseerd zodat de lay-out niet springt.
Voor **Catalogus** geldt dit expliciet: per pagina worden maximaal **10 inhoudelijke catalogusregels** getoond; de tabelcontainer wordt op die 10 inhoudelijke regels gedimensioneerd, zodat productthumbnails geen onbedoelde kortere viewport met extra verticale scroll veroorzaken.
Voor **Voorraad desktop** geldt hetzelfde zichtbare maximum van **10 inhoudelijke regels**; met de 52px-productthumbnail rekent de tabel daarom met een 56px bodyrij. De standaard Voorraadtabel is **25% breder** dan de eerdere baseline (kolombreedtes 55/325/225/150/200/200px) en de omliggende card/contentcontainer mag die breedte zonder vroegtijdig afkappen opnemen.

- zoek- en filterregel staat direct boven de kolomtitels;
- eerste zoekveld heet `Zoek`;
- filters tonen `Filter` zonder extra label erboven wanneer het bestaande tabelpatroon dat gebruikt;
- niet-numerieke kolommen zijn links uitgelijnd;
- numerieke kolommen zijn rechts uitgelijnd;
- checkboxkolommen zijn gecentreerd;
- titel, filter en cellen van één kolom gebruiken exact dezelfde uitlijning;
- Nederlandse decimaalnotatie wordt gebruikt waar van toepassing;
- sortering is beschikbaar waar het tabelcontract dit voorschrijft;
- tabelheaders gebruiken `--color-ui-primary` (standaard `#005F6A`) met witte tekst; sorteerindicatoren op de header zijn eveneens wit en resize-indicatoren blijven visueel herkenbaar;
- actieve kolom/focus op lichte surfaces gebruikt de donkere brand-ink;
- horizontale scroll is toegestaan wanneer responsive reductie anders inhoud verbergt;
- hergebruik `Table`/`DataTable` en bestaande resize-/filterpatronen;
- wanneer een tabel intern verticaal scrolt, blijven de kolomtitelrij en de zoek-/filterrij samen als één sticky kopblok zichtbaar; de titelrij staat op `top: 0` en de zoek-/filterrij blijft direct onder de titelrij op de gemeten of centrale headerhoogte, zonder schermspecifieke sticky-hack.
- dit sticky kopblok is het generieke tabelpatroon voor alle schermen die titel- én zoek/filterrij tonen; schermen activeren het patroon via de centrale tabelklassen in plaats van lokale positionerings-CSS.

### Tabel-loadingoverlay

- bij het laden of verversen van tabelgegevens wordt de blokkerende loading-overlay pas zichtbaar nadat de laadstatus **1.000 ms onafgebroken** actief is; kortere laadacties tonen geen overlay-flits;
- gebruik hiervoor de centrale `DelayedTableLoadingOverlay`; feature-specifieke letter-, spinner- of cirkelvarianten zijn niet toegestaan;
- de overlay toont uitsluitend het dedicated **groene Inhuis-beeldmerk zonder woordmerk** (`/inhuis-loading-mark.svg`), dus geen losse letter `R`, geen cirkelkader en geen zichtbare tekst onder het logo;
- op een regulier desktopvenster is het laadbeeldmerk **420px breed** en responsief begrensd tot maximaal `80vw`, zodat het ook bij browserzoom duidelijk als groot Inhuis-beeldmerk herkenbaar blijft;
- zodra laden gereed is of faalt verdwijnt de overlay direct;
- dezelfde vertraagde overlay wordt ook gebruikt voor langdurige interactieve Catalogus-acties, waaronder het ophalen/controleren van een GPC-classificatie en het zoeken naar GPC Bricks; ook daar verschijnt het beeldmerk pas na 1.000 ms onafgebroken wachten;
- de overlay gebruikt `role="status"`, `aria-busy="true"` en een niet-zichtbaar toegankelijk laadlabel; animatie wordt uitgeschakeld bij `prefers-reduced-motion`.

## Iconen en toegankelijkheid

- iconen zijn functioneel, eenvoudig en consistent;
- iconen tellen niet mee als één van de twee tekstgroottes wanneer zij als icoon zijn gemarkeerd;
- klikbare iconen hebben een bruikbaar touch-/klikgebied;
- interactieve elementen hebben een zichtbare focusstatus;
- kleur is nooit het enige signaal voor betekenis;
- tekst en iconen op `#005F6A` gebruiken `#FFFFFF`, conform de applicatiebrede primaire-foregroundregel;
- leesbaarheid en contrast gaan voor decoratieve transparantie.

## Centrale componenten en verplichte hergebruikroute

De machineleesbare catalogus `frontend/src/ui/componentCatalog.js` is de technische bron voor reeds goedgekeurde herbruikbare UI-componenten. Nieuwe of aangepaste schermen raadplegen deze catalogus **vóór** lokaal UI-code wordt toegevoegd.

Actueel expliciet goedgekeurd en herbruikbaar zijn onder meer:
- `AppFeedbackProvider/useAppFeedback` — tijdelijke meldingen en interactieve feedbackdialogen;
- `Button` — primaire/secundaire acties;
- `Select` — gebruikerszichtbare dropdowns;
- `SearchCandidateList` + `searchCandidatePolicy` — directe zoekkandidaten;
- `CatalogArticleThumbnail` — operationele productthumbnail met fallback;
- `DelayedTableLoadingOverlay` — loadingoverlay na 1.000 ms;
- `Table`/`DataTable` — canonieke tabellen;
- `MobileModuleHeader` — compacte mobiele moduleheader;
- `MobileBackControl` via `MobileAppChrome` — één centrale terugactie linksboven op ieder beveiligd mobiel scherm;
- `MobileRecentActionsBar` — vaste recente-actiebalk onderin ieder beveiligd mobiel scherm;
- `QuantityStepper` — canonieke `− waarde +`-bediening met optionele directe numerieke aantalinvoer; domeinmutaties en de beslissing of inline bewerken veilig is blijven buiten het component.

Harde werkwijze:
1. bestaand goedgekeurd component dat functioneel past wordt hergebruikt;
2. een scherm maakt geen lokale kopie/variant voor alleen spacing, kleur, label of kleine presentatieverschillen;
3. als geen bestaand component past, wordt een nieuw gedeeld component onder `frontend/src/ui/` gemaakt wanneer het patroon herbruikbaar is;
4. ieder nieuw centraal component krijgt in dezelfde wijziging een catalogus-entry met **purpose**, **reuseRule**, publieke API en contracttests;
5. nieuwe schermspecifieke lokale componenten zijn alleen toegestaan wanneer het patroon aantoonbaar niet herbruikbaar is;
6. `frontend/tests/ui-component-reuse.contract.mjs` faalt wanneer een nieuw centraal JSX-component niet is gecatalogiseerd of wanneer een gemigreerd referentiescherm een verplichte centrale component niet meer gebruikt.

De catalogus bevat ook bestaande UI-modules die nog niet als expliciet PO-goedgekeurd hergebruikcomponent zijn geclassificeerd. Zij mogen niet stilzwijgend als nieuwe standaard worden gekopieerd; bij aanraking worden zij beoordeeld en zo nodig bevorderd naar een gespecificeerd component.

## Kernflowconsistentie

De mobiele kernflow **Voorraad → Bijna op → Boodschappenlijst → Kassa → Uitpakken** migreert gefaseerd naar de nieuwe ontwerpbaseline. Daardoor is tijdelijke visuele variatie tussen **Voorraad** en nog niet gemigreerde schermen toegestaan.

Tijdens deze overgang:
- functionele routes, autorisatie, data-identiteit en domeinacties blijven ongewijzigd;
- **Voorraad** is de visuele bron voor volgende migraties;
- niet-gemigreerde schermen worden niet opportunistisch meegewijzigd in een Voorraad-PR;
- nieuwe schermwijzigingen kopiëren geen inmiddels vervallen Voorraad-wallpaper/glassmorphism/sticky-CTA-patroon;
- bij iedere volgende migratie wordt de canonieke styleguide in dezelfde PR bijgewerkt.

### Mobiele Voorraad — aantalbediening

- de `−`, waarde- en `+`-bediening gebruikt touchdoelen van minimaal **44 × 44px**;
- tussen de `+`-bediening en de `>`-navigatie staat extra visuele/tactiele ruimte; de mobiele Voorraadbaseline gebruikt **14px** tussen de stepper en de chevron;
- een tik op het aantal mag **nooit** doorbubbelen naar de artikeldetailnavigatie;
- een klikbare Voorraadkaart en de detailchevron `>` tonen op pointer-apparaten `cursor: pointer`; bij hover krijgt de chevron een subtiele teal/groene nadruk zodat zichtbaar is dat dit de detailnavigatie is;
- wanneer de zichtbare regel exact één onderliggende voorraadregel heeft en de gebruiker mag muteren, is het aantal direct numeriek bewerkbaar; `inputMode="decimal"` opent op ondersteunde telefoons het numerieke toetsenbord en Enter/veld verlaten bevestigt de nieuwe exacte waarde;
- directe aantalinvoer gebruikt dezelfde bestaande huishoudartikel-`inventory-events` authority en maakt geen parallel voorraadmodel;
- wanneer één zichtbare Voorraadregel meerdere onderliggende voorraadlocaties samenvoegt, wordt het samengevoegde totaal niet inline als één locatie overschreven; de waarde blijft wel een afgeschermd niet-navigerend touchgebied en locatiegerichte aanpassing verloopt via het artikeldetail.

## Mobiele Boodschappenlijst

De mobiele **Boodschappenlijst** is een responsive presentatie van de bestaande actieve shopping-list en introduceert geen parallel domeinmodel. Interne route-, permissie- en technische sleutels mogen `winkelen` blijven heten.

Vaste regels:
- desktop `/winkelen` behoudt de bestaande `DataTable`; reguliere huishoudgebruikers krijgen op `<=720px` de mobiele presentatie;
- dezelfde bestaande shopping-list endpoints en permissies blijven de enige functionele authority;
- bovenaan staat uitsluitend het blok **Artikel toevoegen**; na minimaal twee zoektekens verschijnen maximaal **5 kandidaten direct onder het zoekveld**, zonder extra klik op een gesloten resultaatselectie;
- de compacte **Mijn lijst**-contextcard staat direct vóór de reeds geselecteerde artikelen en toont totaal aantal regels en aantal **nog te kopen**;
- het afzonderlijke mobiele blok **Zoek in je winkellijst / Producttype / Sorteren / Filters wissen** wordt niet getoond;
- de daadwerkelijke lijst heeft één functionele titel: **Boodschappenlijst**; een fallbackkop zoals **Niet ingedeeld** wordt niet als lijsttitel getoond;
- iedere kaart toont minimaal gekochtstatus, artikelnaam en **Aantal**, met producttype, echte artikelgroep, omvang en opmerking wanneer aanwezig;
- **Aantal**, **Omvang** en **Opmerking** blijven bewerkbaar via dezelfde bestaande update-route;
- wanneer dezelfde canonieke kandidaat opnieuw wordt toegevoegd, blijft één regel zichtbaar en wordt **Aantal** verhoogd; gelijke namen met verschillende bronidentiteit worden niet stil samengevoegd;
- regels blijven selecteerbaar voor de bestaande acties **Exporteren** en **Verwijderen**;
- **Winkelen afgerond** blijft de dominante sticky primaire afrondactie boven eventuele tijdelijke feedbackoverlay en gebruikt dezelfde bestaande complete-route;
- passieve succesfeedback verschijnt via de centrale mobiele AppFeedback-overlay; verwijder- en afrondbevestigingen blijven interactieve AppFeedback-dialogen;
- content reserveert onderaan de vaste navigatie/actie plus safe-area, zodat de laatste kaart en sticky actie volledig bereikbaar blijven.

Niet tonen zolang hiervoor geen echte appfunctionaliteit bestaat:
- tabs of secties **Suggesties**, **Aanbiedingen** of **Vaak gekocht**;
- winkelgroepering of winkelsortering op een shopping-list-regel;
- productafbeeldingen zonder bestaande productbeeldbron of zonder canonieke koppeling naar een Catalogusproduct;
- plus/min-bediening voor Aantal wanneer die niet als bestaande domeinactie is geïmplementeerd.

## Mobiel Voorraad-artikeldetail

Het mobiele detailscherm van een voorraadartikel is een vereenvoudigde presentatie van bestaande Voorraad-functionaliteit en introduceert geen parallel domeinmodel.

Vaste regels:
- het scherm gebruikt hetzelfde huishoudartikel en dezelfde voorraad-/historie-/settings-API's als het bestaande desktop-detailscherm;
- het detailscherm gebruikt dezelfde **groene Voorraadbaseline** als het mobiele hoofdscherm: `MobileModuleHeader` met titel **Artikel in Voorraad**, `/inhuis-green-wallpaper.svg`, achtergrond `#EEF7F0`, witte kaarten met 12px-radius en zonder glassmorphism of zware schaduw;
- terugnavigatie komt uitsluitend uit de gedeelde knop **Terug** van `MobileAppChrome`; het detailscherm en zijn header hebben geen eigen `‹ Voorraad`- of andere terugknop;
- de artikelkop toont waar beschikbaar dezelfde representatieve `CatalogArticleThumbnail`, de artikelnaam en artikelgroep/statuschips;
- de actuele voorraad staat in dezelfde artikelkaart met de centrale `QuantityStepper`;
- `−` verlaagt de voorraad met één via de bestaande afboek-/inventory-eventlogica;
- `+` verhoogt de voorraad met één via de bestaande handmatige voorraadcorrectie;
- wanneer exact één voorraadregel actief is, of wanneer bij meerdere locaties expliciet één locatie is geselecteerd, is het zichtbare aantal direct numeriek bewerkbaar via dezelfde bestaande `inventory-events`-authority; het mobiele numerieke toetsenbord wordt via de gedeelde `QuantityStepper` gebruikt;
- aparte snelle acties **Voorraad aanpassen** en **Afboeken** worden niet getoond;
- de rij **Locatie** wordt alleen getoond wanneer **Waar Inhuis** actief is (`location_tracking_level != none`);
- bij meerdere actieve voorraadlocaties bepaalt de geselecteerde locatie op welke voorraadrij `+`, `−` en directe aantalinvoer werken;
- detail- en actierijen gebruiken dezelfde compacte 14px/16px typografie, neutrale scheidingslijnen en teal `#005F6A` interactiekleur als Mobiele Voorraad;
- **Notities** is een altijd zichtbaar vrij tekstveld; ieder lid van het actieve huishouden, inclusief de rol **Kijker**, mag de gedeelde huishoudnotitie wijzigen; deze uitzondering geeft geen wijzigingsrecht op andere artikel- of huishoudinstellingen;
- **Voorkeurswinkel** gebruikt de centrale `Select` als overlay-dropdown met beschikbare winkels en blijft een beheerinstelling; het openen van de keuzelijst verandert de hoogte of positie van de omliggende detailcontent niet;
- iedere artikelpresentatie via de gedeelde `CatalogArticleThumbnail` toont bij ontbrekende of fout geladen afbeelding zichtbaar **Geen foto**;
- het detailscherm heeft geen vaste algemene `Opslaan`-knop; een specifieke instelling wordt direct/expliciet opgeslagen vanuit zijn eigen interactie;
- de gebruikerszichtbare term voor de shoppingmodule en de lijst is **Boodschappenlijst**; interne route en technische sleutel mogen `winkelen` blijven.

De sectie **Snelle acties** bevat precies:
1. **Voorkeurswinkel** — toont/bewerkt de bestaande huishoudinstelling `favorite_store`;
2. **Aankoophistorie** — toont uitsluitend aankoopgebeurtenissen van het huidige huishoudartikel;
3. **Op boodschappenlijst** — voegt het huidige huishoudartikel direct toe aan de actieve **Boodschappenlijst**, opent geen extra detailscherm en geeft feedback via de centrale mobiele AppFeedback-overlay.

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

## Mobiele UI-conformiteit tijdens de redesign

De mobiele redesign gebruikt vanaf 23 september 2026 een gescheiden testmodel:

- functionele mobiele contracttests blijven routes, data, API-gebruik, autorisatie, domeinacties en noodzakelijke interacties bewaken;
- historische visuele assertions van nog niet gemigreerde mobiele schermen zijn geen actuele UI-authority en mogen een nieuw schermontwerp niet blokkeren;
- de actuele visuele authority voor gemigreerde mobiele modulehoofschermen staat in `frontend/tests/mobile-ui-conformity.contract.mjs`;
- die conformiteitstest bevat uitsluitend schermen waarvoor de PO de nieuwe baseline expliciet heeft vastgesteld;
- bij iedere volgende mobiele schermmigratie wordt dezelfde conformiteitstest met de nieuwe schermbaseline uitgebreid en worden eventuele resterende legacy-visuele assertions voor dat scherm verwijderd;
- functionele regressiedekking wordt daarbij niet verlaagd of omzeild: alleen de vervangen visuele baseline verhuist naar de nieuwe authority.

Op dit moment vallen **Voorraad** en **Voorraad-artikeldetail** onder de nieuwe mobiele UI-conformiteitsset. **Bijna op** en **Boodschappenlijst/Winkelen** behouden hun functionele regressietests, maar hebben totdat hun nieuwe ontwerp expliciet is vastgesteld geen blokkerende legacy-visuele baseline.

## Historische styleguidedocumenten

`docs/Rezzerv-Styleguide_v05.08.md` en `Rezzerv-Styleguide_v05.14.md` blijven behouden als audittrail van eerdere PO-besluiten. Hun actuele regels zijn hierboven geconsolideerd. Nieuwe wijzigingen worden niet als nieuwe losse styleguideversies toegevoegd tenzij de PO daar expliciet om vraagt; de canonieke bron wordt direct bijgewerkt.
