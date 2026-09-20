# Inhuis UI-styleguide

Status: **canonieke UI-bron** voor gebruikerszichtbare vormgeving en interactiepatronen in Inhuis.  
Laatst inhoudelijk vastgesteld door de PO: 20 september 2026.

Deze styleguide is de actuele leesbare UI-bron voor nieuwe schermen en wijzigingen aan bestaande schermen. Historische styleguidedocumenten blijven audittrail, maar nieuwe UI-beslissingen worden hier geconsolideerd. Bij een conflict met een oudere UI-notitie geldt deze canonieke styleguide, tenzij de PO expliciet een nieuwere afwijking heeft vastgesteld.

De actuele mobiele visuele baseline wordt gevormd door twee door de PO beoordeelde schermtypen:
- **Voorraad** als referentie voor mobiele lijst-, zoek- en filterschermen;
- **Voorraad-artikeldetail** als referentie voor mobiele detail-, veld- en snelle-actieschermen.

Nieuwe mobiele kernschermen sluiten aantoonbaar aan op deze twee referenties, tenzij de PO expliciet een afwijkend patroon vaststelt.

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
- `--color-brand-primary`: `#1A3E2B` — donkere brand-ink voor tekst, iconen en focus op lichte surfaces;
- `--color-ui-primary`: `#28A99E` — primaire blauw-groene UI-kleur voor dominante gekleurde surfaces;
- `--color-ui-primary-text`: `#FFFFFF` — witte tekst en iconen op primaire blauw-groene surfaces;
- `--color-brand-light`: `#D9F5E0`;
- `--color-text-primary`: `#1A1A1A`;
- `--color-text-inverse`: `#FFFFFF`;
- `--color-border-default`: `#CFE8D6`;
- `--color-table-grid`: `#8FD19E`.

Gebruik:
- `#28A99E` is de primaire Inhuis-UI-kleur voor header, primaire gekleurde acties, tabelheaders en de meldingenbalk;
- tekst en iconen op `#28A99E` gebruiken centraal `#FFFFFF`; dit geldt applicatiebreed voor primaire gekleurde surfaces en vervangt de eerdere donkere tekstkleur;
- `#1A3E2B` blijft de brand-ink voor tekst, iconen, focus/accent en geselecteerde status op lichte of witte surfaces;
- normale tekst gebruikt de primaire donkere tekstkleur;
- lichte groentinten zijn ondersteunend en concurreren niet met de primaire actie;
- de legacy-token `--rz-accent` wordt centraal gekoppeld aan `--color-ui-primary`;
- voeg geen nieuwe dominante merkkleur toe zonder expliciete PO-beslissing en styleguide-update;
- witte tekst op primaire gekleurde surfaces geldt voor **alle schermen** en omvat minimaal headers, permanente footer-/meldingenbalken, primaire en secundaire gekleurde knoppen en de gekleurde titelrij van tabellen;
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
2. zoeken/filteren/context of een compacte hero/contextcard;
3. hoofdinhoud in cards/lijst/tabel of detailsecties;
4. één dominante primaire actie waar nodig;
5. permanente onderste meldingenbalk; tijdelijke feedback verschijnt in die balk.

Alle onderdelen volgen één horizontale uitlijning en herhaalbare spacing. Een scherm introduceert geen eigen navigatie- of actiepatroon wanneer een bestaand centraal patroon beschikbaar is.

Voor de twee mobiele referentieschermen geldt daarnaast:
- de hoofdinhoud staat gecentreerd en wordt niet breder dan `720px`;
- op smalle mobiele breedtes is circa `10px` horizontale buitenruimte de referentie; op ruimere mobiele breedtes circa `14px`;
- opeenvolgende cards/lijstitems houden een rustig, herhaalbaar verticaal ritme van ongeveer `10–12px` aan;
- de scherminhoud reserveert onderaan altijd voldoende scrollruimte voor de permanente meldingenbalk en eventuele safe-area.

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
- achtergrond: `--color-ui-primary` (`#28A99E`);
- schermtitel en subtitel gebruiken wit (`--color-ui-primary-text`, `#FFFFFF`);
- op mobiel staat de schermtitel links en het witte Inhuis-logo rechts;
- secundaire headercontext zoals subtitel/userbox wordt op het compacte mobiele patroon niet tussen titel en logo gepropt;
- gebruikerszichtbaar merk is **Inhuis**;
- het witte Inhuis-logo staat rechts, is verticaal gecentreerd en blijft volledig binnen de header;
- interne technische naamgeving `Rezzerv` mag in code blijven maar wordt niet als gebruikersmerk getoond.

## Mobiele achtergrond en surfaces

De mobiele Voorraad-weergave is de visuele referentie voor de kernflow:
- lichtgroen, zacht gevlekt en laag in contrast;
- asset `/inhuis-green-wallpaper.svg`;
- basisachtergrond `#EEF7F0`;
- cards en filter-/zoekoppervlakken zijn wit of vrijwel wit en duidelijk leesbaar boven de achtergrond;
- mobiele cards gebruiken een rustige lichte rand, royale afronding en een zachte groengetinte schaduw; zware zwarte schaduwen passen niet bij de referentie;
- achtergronddecoratie concurreert nooit met tekst of bediening;
- transparantie/blur mag ondersteunend worden gebruikt, maar leesbaarheid en contrast gaan voor.

De eerdere oranje achtergrond is geen actuele visuele referentie meer.

## Mobiele referentieschermen

De huidige schermen **Voorraad** en **Voorraad-artikeldetail** zijn samen de concrete visuele baseline voor verdere mobiele kernschermen. Zij delen dezelfde shell maar gebruiken twee verschillende inhoudspatronen.

### Referentie A — mobiele lijstweergave: Voorraad

Gebruik dit patroon voor schermen waar de gebruiker zoekt, filtert en een item uit een verzameling kiest.

Vaste kenmerken:
- bovenaan staat na de header één witte zoek-/filtercard;
- het zoekveld krijgt de meeste breedte en staat visueel als eerste ingang van de lijst;
- zoek-, select- en filtervelden hebben minimaal circa `44px` touchhoogte; een prominent zoekveld mag circa `50px` hoog zijn;
- een compacte status-/aantalbadge mag tussen filtercard en lijst staan, maar blijft visueel ondergeschikt aan de primaire actie;
- lijstitems zijn witte afgeronde cards met één duidelijk klikdoel over de gehele card;
- primaire itemnaam staat links als hoofdnadruk; artikelgroep/metadata staat daaronder in lichtere chip-/metadatavorm;
- hoeveelheid/status staat rechts in een compacte pill en een chevron maakt navigatie herkenbaar;
- een lijstitem heeft voldoende touchhoogte; de huidige Voorraadreferentie gebruikt ongeveer `80px` of meer;
- lijstitems staan met ongeveer `10px` verticale tussenruimte onder elkaar;
- één schermbrede primaire vervolgactie mag onder de lijst sticky zijn, maar moet volledig boven de permanente meldingenbalk kunnen komen en bereikbaar blijven door te scrollen.

### Referentie B — mobiel detailscherm: Voorraad-artikeldetail

Gebruik dit patroon voor een enkel object met actuele status, velden en gerichte vervolghandelingen.

Vaste kenmerken:
- de eerste card is een compacte hero/contextcard met objectnaam/status links en directe kernbediening rechts;
- directe plus/min-bediening gebruikt minimaal `44 × 44px` touchdoelen;
- aanvullende informatie staat in afzonderlijke witte sectiecards met duidelijke `16px` sectietitel;
- veldachtige detailregels zijn tweekoloms: label links, waarde/status rechts;
- detail- en actierijen hebben links en rechts minimaal `1ch` interne ademruimte;
- snelle acties zijn als volledige rij klikbaar waar passend; de belangrijkste vervolgstap mag als volle blauw-groene rij/knop worden weergegeven;
- waarden rechts mogen semibold zijn om scanbaarheid te verbeteren, zonder een derde tekstgrootte te introduceren;
- cards volgen hetzelfde horizontale ritme, dezelfde lichte surfacefamilie en dezelfde achtergrond als de lijstweergave.

### Gedeelde mobiele shell

Voor beide referenties geldt:
- `64px` blauw-groene header op mobiel;
- `#28A99E` voor header, primaire actie en permanente meldingenbalk;
- witte tekst/iconen (`#FFFFFF`) op primaire blauw-groene surfaces;
- lichtgroen gevlekte pagina-achtergrond;
- witte of vrijwel witte contentcards;
- uitsluitend `14px` bodytekst en `16px` titel/hoofdnadruk in de uiteindelijke rendering;
- minimaal circa `44px` voor primaire touchdoelen;
- permanente meldingenbalk van `64px` onderin;
- document-/scrollinhoud reserveert minimaal de balkhoogte plus `env(safe-area-inset-bottom)` zodat de laatste inhoud of actie volledig boven de balk kan worden gebracht;
- sticky acties gebruiken een bottom-offset boven de meldingenbalk en mogen niet achter de balk eindigen;
- browserzoom of responsive emulatie mag deze basisafstand, `1ch`-veldmarges of bereikbaarheid van de onderste actie niet laten verdwijnen.

Deze twee schermen zijn een **patroonreferentie**, geen opdracht om functionele inhoud letterlijk te kopiëren. Nieuwe modules gebruiken dezelfde visuele grammatica met hun eigen domeininhoud.

## Meldingen en feedback

Voor passieve applicatiemeldingen geldt één centraal patroon:
- succes-, fout-, waarschuwing-, informatie- en voortgangsmeldingen worden niet midden in het scherm geplaatst;
- zij verschijnen in een vaste onderste balk over de volle schermbreedte;
- de balk is permanent zichtbaar, ook wanneer er geen melding is; zonder melding blijft de balk leeg en toont hij geen placeholdertekst;
- de balk heeft dezelfde hoogte als de header: `58px` op grotere schermen en `64px` op mobiel;
- achtergrond is `#28A99E` en tekst/iconen zijn wit (`#FFFFFF`);
- bij een melding verschijnt de feedbackinhoud op dezelfde balklaag;
- de melding mag een compacte OK- of detailactie bevatten zolang de balkhoogte gelijk blijft;
- technische details mogen op verzoek boven de balk worden uitgeklapt, maar de meldingenbalk zelf verandert niet van hoogte;
- tijdelijke mobiele artikelfeedback volgt hetzelfde patroon;
- de permanente balk ligt visueel boven de pagina-inhoud, maar mag functioneel nooit de laatste content of actie onbereikbaar maken;
- iedere mobiele scrollcontext reserveert daarom onderaan minimaal de balkhoogte plus eventuele safe-area; de scrollbar moet ver genoeg doorlopen om de laatste actie volledig boven de balk te brengen.

Interactieve dialogen waarin de gebruiker gegevens moet invoeren of een expliciete keuze moet bevestigen blijven dialogen; zij zijn geen passieve melding en worden niet in de onderste balk gepropt.

## Zoeken, invoer en filters

- zoek- en filtervelden hebben dezelfde visuele familie;
- tekst is `14px`;
- gebruikerszichtbare dropdowns gebruiken de centrale Inhuis-`Select`-component; native browser/OS-`<select>`-popups zijn voor deze schermen niet toegestaan omdat hun geopende optielijst de Inhuis-typografie niet betrouwbaar volgt;
- de centrale Inhuis-`Select` gebruikt voor veldwaarde én alle opties in de geopende lijst exact `14px`, gelijk aan de veldlabels;
- de geopende Inhuis-`Select` wordt als overlay op de centrale applicatielaag gerenderd en ligt altijd vóór de onderliggende cards, lijsten en tabellen; stacking contexts van de inhoud mogen de dropdown niet afdekken;
- bij **zoekgestuurde kandidaatselectie** worden gevonden kandidaten direct onder het zoekveld zichtbaar; de gebruiker hoeft niet eerst een gesloten resultaatveld of dropdown te openen;
- zo'n zoekkandidatenlijst toont maximaal **5 kandidaten** tegelijk en gebruikt de centrale `SearchCandidateList`/`searchCandidatePolicy`; dit geldt applicatiebreed, waaronder Boodschappenlijst, Voorraad-autocomplete, handmatige externe productzoeking en Catalogus/GPC-zoeking;
- automatische GS1 GPC-classificatie toont bij een nog ongeclassificeerd Catalogusartikel maximaal **5 direct zichtbare kandidaten**, gerangschikt op indicatieve matchsterkte; iedere kandidaat toont minimaal Brickcode, omschrijving, hiërarchie en een korte reden voor de match, en kan afzonderlijk worden bevestigd of genegeerd;
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

Een standaard listcard bevat:
- primaire informatie links;
- secundaire metadata/chips onder of naast de primaire tekst;
- status/aantal/chevron aan de rechterkant wanneer relevant;
- één duidelijk klikdoel per rij, bij voorkeur de hele card;
- witte of bijna-witte surface met rustige rand/schaduw;
- consistente padding en afronding.

De primaire itemnaam mag `16px` gebruiken als hoofdnadruk; overige tekst blijft `14px`.

## Productafbeeldingen

- productafbeeldingen uit externe productbronnen worden als ondersteunende productidentificatie getoond en vervangen nooit de artikelnaam of GTIN;
- Cataloguslijsten gebruiken waar beschikbaar een compacte thumbnail naast de artikelnaam, zonder een extra brede fotokolom af te dwingen;
- Catalogusdetail mag dezelfde afbeelding groter tonen met behoud van beeldverhouding en `object-fit: contain`;
- ontbrekende of niet-laadbare afbeeldingen krijgen een rustige **Geen foto**-fallback zonder broken-image-icoon;
- een externe afbeelding-URL wordt niet automatisch gebruikt om een reeds aanwezige Catalogusafbeelding te overschrijven.

## Badges, chips en aantallen

- badges/chips gebruiken `14px`; zij ogen compacter door padding, achtergrond en gewicht, niet door kleinere tekst;
- aantallen gebruiken eveneens `14px`;
- pill-/chipvormen zijn ondersteunend en mogen niet sterker concurreren dan de primaire schermactie;
- numerieke aantallen mogen tabular numerals gebruiken.

## Knoppen en acties

- primaire knop: `#28A99E` met witte tekst/iconen (`#FFFFFF`);
- knoptekst is `14px` en niet vet (`font-weight: 400`);
- per scherm is bij voorkeur één dominante primaire actie;
- secundaire acties krijgen minder visueel gewicht;
- volledige-breedteknoppen zijn op mobiel passend wanneer één duidelijke vervolgstap centraal staat;
- disabled-, hover-, active- en focusstatus zijn zichtbaar en consistent;
- de primaire actie mag sticky onderaan staan als dit content en meldingenbalk niet blokkeert;
- een sticky mobiele actie krijgt expliciet voldoende bottom-offset boven de permanente meldingenbalk en de scrollcontainer reserveert daarnaast voldoende eindruimte om de actie volledig zichtbaar en bereikbaar te maken.

## Tabellen

De standaard desktop-/matrixweergave toont waar een tabel pagineert **10 zichtbare bodyregels** per pagina. Wanneer minder dan 10 records beschikbaar zijn, mag de tabelhoogte met lege niet-interactieve fillerregels op 10 regels worden gestabiliseerd zodat de lay-out niet springt.

- zoek- en filterregel staat direct boven de kolomtitels;
- eerste zoekveld heet `Zoek`;
- filters tonen `Filter` zonder extra label erboven wanneer het bestaande tabelpatroon dat gebruikt;
- niet-numerieke kolommen zijn links uitgelijnd;
- numerieke kolommen zijn rechts uitgelijnd;
- checkboxkolommen zijn gecentreerd;
- titel, filter en cellen van één kolom gebruiken exact dezelfde uitlijning;
- Nederlandse decimaalnotatie wordt gebruikt waar van toepassing;
- sortering is beschikbaar waar het tabelcontract dit voorschrijft;
- tabelheaders gebruiken `#28A99E` met witte tekst; sorteerindicatoren op de header zijn eveneens wit en resize-indicatoren blijven visueel herkenbaar;
- actieve kolom/focus op lichte surfaces gebruikt de donkere brand-ink;
- horizontale scroll is toegestaan wanneer responsive reductie anders inhoud verbergt;
- hergebruik `Table`/`DataTable` en bestaande resize-/filterpatronen.

### Tabel-loadingoverlay

- bij het laden of verversen van tabelgegevens wordt de blokkerende loading-overlay pas zichtbaar nadat de laadstatus **1.000 ms onafgebroken** actief is; kortere laadacties tonen geen overlay-flits;
- gebruik hiervoor de centrale `DelayedTableLoadingOverlay`; feature-specifieke letter-, spinner- of cirkelvarianten zijn niet toegestaan;
- de overlay toont uitsluitend het bestaande **Inhuis-beeldmerk zonder woordmerk** (`/inhuis-app-icon.png`), dus geen losse letter `R`, geen cirkelkader en geen zichtbare tekst onder het logo;
- op een regulier desktopvenster is het beeldmerk **250px breed**, exact vijfmaal de 50px-basishoogte van het Inhuis-logo in de desktopheader; op smallere vensters mag het responsief begrensd worden tot maximaal `70vw`;
- zodra laden gereed is of faalt verdwijnt de overlay direct;
- de overlay gebruikt `role="status"`, `aria-busy="true"` en een niet-zichtbaar toegankelijk laadlabel; animatie wordt uitgeschakeld bij `prefers-reduced-motion`.

## Iconen en toegankelijkheid

- iconen zijn functioneel, eenvoudig en consistent;
- iconen tellen niet mee als één van de twee tekstgroottes wanneer zij als icoon zijn gemarkeerd;
- klikbare iconen hebben een bruikbaar touch-/klikgebied;
- interactieve elementen hebben een zichtbare focusstatus;
- kleur is nooit het enige signaal voor betekenis;
- tekst en iconen op `#28A99E` gebruiken `#FFFFFF`, conform de applicatiebrede primaire-foregroundregel;
- leesbaarheid en contrast gaan voor decoratieve transparantie.

## Centrale componenten

Nieuwe schermen hergebruiken waar passend bestaande centrale componenten en patronen, waaronder:
- `AppShell`;
- header/branding;
- `AppFeedbackProvider` voor passieve applicatiemeldingen;
- `Card`;
- `Button`;
- `Select` voor gebruikerszichtbare dropdowns waarvan de geopende lijst de Inhuis-typografie moet volgen;
- `SearchCandidateList` plus `searchCandidatePolicy` voor automatisch zichtbare zoekkandidaten (maximaal 5);
- inputs/search;
- listcard-/badge-/statuspatronen;
- `Table`/`DataTable`;
- `ResizableHeaderCell`;
- bestaande loading-, empty- en errorstates.

Maak geen lokale variant van een bestaand component alleen om kleine visuele verschillen te realiseren.

## Kernflowconsistentie

Voor de mobiele kernflow **Voorraad → Bijna op → Boodschappenlijst → Kassa → Uitpakken** gelden dezelfde:
- typografie;
- merk- en surfacekleuren;
- lichtgroen gevlekte achtergrond waar de kernflow die achtergrond gebruikt;
- spacinglogica en mobiele `1ch`-binnenmarge;
- zoek-/filtertaal;
- card- en statuspatronen;
- primaire-actielogica;
- permanente onderste meldingenbalk met verplichte scroll-clearance;
- focus- en touchregels.

Functionele verschillen tussen deze schermen mogen zichtbaar zijn, maar ze voelen als één applicatie en niet als losse modules.

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
- **Winkelen afgerond** blijft de dominante sticky primaire afrondactie boven de permanente meldingenbalk en gebruikt dezelfde bestaande complete-route;
- passieve succesfeedback verschijnt via de centrale onderste meldingenbalk; verwijder- en afrondbevestigingen blijven interactieve AppFeedback-dialogen;
- content reserveert onderaan de meldingenbalk plus safe-area, zodat de laatste kaart en sticky actie volledig bereikbaar blijven.

Niet tonen zolang hiervoor geen echte appfunctionaliteit bestaat:
- tabs of secties **Suggesties**, **Aanbiedingen** of **Vaak gekocht**;
- winkelgroepering of winkelsortering op een shopping-list-regel;
- productafbeeldingen zonder bestaande productbeeldbron;
- plus/min-bediening voor Aantal wanneer die niet als bestaande domeinactie is geïmplementeerd.

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
- de gebruikerszichtbare term voor de shoppingmodule en de lijst is **Boodschappenlijst**; interne route en technische sleutel mogen `winkelen` blijven.

De sectie **Snelle acties** bevat precies:
1. **Voorkeurswinkel** — toont/bewerkt de bestaande huishoudinstelling `favorite_store`;
2. **Aankoophistorie** — toont uitsluitend aankoopgebeurtenissen van het huidige huishoudartikel;
3. **Naar inkooplijstje** — voegt het huidige huishoudartikel direct toe aan de actieve **Boodschappenlijst**, opent geen extra detailscherm en geeft feedback via de onderste meldingenbalk.

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
