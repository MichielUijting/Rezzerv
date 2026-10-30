# Inhuis UI-styleguide

Status: **canonieke UI-bron** voor gebruikerszichtbare vormgeving en interactiepatronen in Inhuis.  
Laatst inhoudelijk vastgesteld door de PO: 25 september 2026.
Aanvullend PO-besluit over de uniforme mobiele header en compacte Voorraad: 8 oktober 2026.

Deze styleguide is de actuele leesbare UI-bron voor nieuwe schermen en wijzigingen aan bestaande schermen. Historische styleguidedocumenten blijven audittrail, maar nieuwe UI-beslissingen worden hier geconsolideerd. Bij een conflict met een oudere UI-notitie geldt deze canonieke styleguide, tenzij de PO expliciet een nieuwere afwijking heeft vastgesteld.

De mobiele Voorraadbaseline is op **22 september 2026** ingezet en op **23 september 2026** door de PO verder verfijnd. De actuele variant combineert de rustige vlakke lijststructuur met de lichtgroene gevlekte Inhuis-achtergrond, een mobiele header via de centrale primaire kleurtoken (standaard `#005F6A`) en een gebruikersspecifieke onderste actiebalk. Eerdere Voorraad-borging geldt niet meer wanneer zij met dit nieuwere PO-besluit conflicteert.

Het mobiele **Voorraad-artikeldetail** is op **23 september 2026** naar dezelfde nieuwe mobiele richting gemigreerd. Het hoofdscherm Voorraad blijft de primaire lijstbaseline; het artikeldetail is de actuele detailbaseline voor gedeelde navigatie, kleur en artikelpresentatie.

Historische besluiten die hierin zijn opgenomen:
- `docs/Rezzerv-Styleguide_v05.08.md`: knoptekst is niet vet;
- `Rezzerv-Styleguide_v05.14.md`: niet-numerieke tabelkolommen links, numerieke kolommen rechts, met gelijke uitlijning voor titel/filter/cellen.

## App-brede responsieve UI-selectie vanaf 25 september 2026

De keuze tussen desktop-/tabelpresentatie en een beschikbare mobiele presentatie is **uitsluitend viewport-gestuurd** en geldt app-breed:

- `<=720px` gebruikt de mobiele app-chrome en, waar een scherm al een mobiele variant heeft, die mobiele variant;
- `>720px` gebruikt de desktop-/tabelpresentatie;
- gebruikersrol, Superuser/Beheerder/Gebruiker, platformrechten, huishoudenstype en locatieconfiguratie bepalen **nooit** welke UI-variant wordt gekozen;
- Inhuis toont **geen functionele schakelaar** voor Mobiel/Tabel/Automatisch;
- op desktop/laptop kan de mobiele variant voor testen worden geactiveerd door de browserviewport responsief/smal te maken, bijvoorbeeld via de browser-device-mode (Ctrl+Shift+M waar ondersteund);
- tabletgedrag volgt dezelfde viewportregel; oriëntatie, split-screen of browserweergave kan daardoor de effectieve variant veranderen;
- locatieconfiguratie bepaalt alleen welke locatiegegevens, filters en sorteringen binnen een scherm beschikbaar zijn, niet de keuze van de schermvariant;
- toekomstige responsive schermwrappers gebruiken dezelfde centrale `MOBILE_APP_MEDIA_QUERY`/viewport-hook en introduceren geen eigen rol- of permissiegate voor presentatiekeuze.

## Gedeelde mobiele header en compacte voorraad — 8 oktober 2026

Voor alle **aangemelde Inhuis-schermen** op mobiele viewports (maximaal 720px) geldt één uniforme, sticky applicatieheader:

- De header wordt centraal gerenderd door `MobileAppChrome` via `MobileModuleHeader` en staat boven de scherminhoud, met `position: sticky; top: 0`. De Terug-knop blijft **in de header** zichtbaar tijdens scrollen, links uitgelijnd. De paginatitel staat ernaast en het Inhuis-logo staat rechts.
- De bestaande `BrandLogo` is de enige herbruikbare logobron voor de header; schermen onderhouden geen eigen mobiele woordmerken of afzonderlijke zwevende Terug-knoppen.
- In de mobiele app-shell zijn oude schermheaders niet afzonderlijk zichtbaar; op desktop blijven de bestaande headers en gebruikerscontext onveranderd.
- Dit contract geldt voor alle door de aangemelde router beschermde schermen, waaronder dashboard, Voorraad, Boodschappen, Uitpakken, Catalogus, Instellingen, onboarding, detailpagina's en platformfuncties. Publieke toegangsschermen (login, registratie en wachtwoordherstel) behouden hun eigen toegangspresentatie.
- De gedeelde Terug-knop bewaart bestaande uitzonderingen: vanaf Dashboard vraagt de knop bevestiging voor verlaten/uitloggen en in Kassa krijgt de actuele Kassa-flow eerst de gelegenheid interne navigatie af te handelen.

Voor de **mobiele Voorraadlijst** geldt daarnaast:

- Per artikel worden de classificatieregels `Brick` en `Productfamilie` niet getoond, zodat meer artikelen op het scherm passen. De GS1/GPC-gegevens blijven in het datamodel en bij zoeken beschikbaar.
- De pagineringscomponent heeft een normale tussenruimte van 12px boven de bediening en zit niet direct tegen de lijst.
- Bij gewone plus/min-/exacte voorraadwijzigingen verandert de zichtbare hoeveelheid direct, zonder succesmelding; bij een opslagfout herstelt de vorige hoeveelheid en verschijnt wel een foutmelding. Een geslaagde mutatie vereist geen volledige herlaadactie van de lijst.

## Mobiele Instellingenbaseline vanaf 27 september 2026

Voor **Instellingen** geldt op viewports van maximaal 720px dezelfde centrale mobiele app-chrome als voor de overige beveiligde mobiele schermen:

- de gedeelde **Terug**-knop en bottom-navigation komen uitsluitend uit `MobileAppChrome`; Settings-schermen bouwen geen eigen concurrerende mobiele navigatie;
- het hoofdscherm gebruikt compacte, touchvriendelijke instellingstegels per functionele sectie;
- invoervelden, selecties en primaire acties benutten de beschikbare mobiele breedte en hebben voldoende touchhoogte;
- modals blijven binnen de mobiele viewport en scrollen intern wanneer de inhoud hoger is dan het scherm;
- desktop-tabellen blijven boven 720px ongewijzigd; binnen Instellingen worden tabelrijen op mobiel als verticale kaarten gepresenteerd;
- iedere mobiele tabelcel toont het bijbehorende kolomlabel naast de waarde, zodat informatie niet betekenisloos wordt wanneer de desktopkop verdwijnt;
- kolom-resizebediening is op mobiel niet zichtbaar;
- autorisatie, routes, beschikbare velden en acties zijn identiek aan desktop; responsiviteit mag geen functionele rechten of gegevens verwijderen.

## Mobiel dashboard als landingspagina vanaf 2 oktober 2026

De mobiele landingspagina is vanaf deze wijziging een **dashboard** en geen tweede navigatiemenu:

- de vaste onderste actiebalk blijft de primaire mobiele navigatie naar modules;
- bovenaan het dashboard staat één compacte, horizontale statusregel met **Meldingen**, **Boodschappen** en **Nog opbergen**; ieder statusvlak is volledig aanklikbaar en opent de betreffende functionele flow;
- daaronder staan informatiegerichte dashboardtegels voor **Uitgaven t.o.v. vorig jaar**, **Uitgaven**, **Bezochte winkels** en **Begrote uitgaven**;
- dashboardtegels tonen een kernwaarde, korte vergelijking/context en een compacte grafische weergave;
- boven de grafieken staat één compacte schakelaar **Dagen / Weken / Maanden**; iedere keuze toont exact de laatste vier perioden;
- **Uitgaven t.o.v. vorig jaar** vergelijkt die vier perioden met exact dezelfde perioden één jaar eerder; de vergelijkingswaarden zijn lichtgroen;
- de overige historische vergelijkingsgrafieken vergelijken de vier huidige perioden met de vier direct voorafgaande perioden;
- **alle vier dashboardtegels** reageren op de periodekeuze; de begroting toont overeenkomstig de komende 4 dagen, 4 weken of 4 maanden;
- vergelijkingsgrafieken tonen een zichtbare verticale waarde-as; de actuele periode gebruikt de primaire donkergroene kleur en de vergelijkingsperiode een lichtgroene kleur;
- de tekst **Bekijk details** staat niet in de dashboardtegels; de volledige tegel blijft aanklikbaar;
- de gebruiker kan een dashboardgrafiek verslepen met muis of door aanraken en bewegen op het grafiekvlak; de overige grafieken herschikken direct;
- de dashboardvolgorde wordt per gebruiker lokaal bewaard en bij terugkeer naar het dashboard opnieuw toegepast;
- **Begrote uitgaven** wordt niet afgeleid van een simpel historisch weekgemiddelde, maar van verwachte **herhalingskoop** per artikel op basis van het historische koopritme en het verwachte volgende koopmoment;
- de status **Nog opbergen** opent rechtstreeks **Kassa > Bonnen** en niet de camera;
- de globale onderste actie **Meer** opent een apart overzicht met de overige beschikbare hoofdfuncties die niet al als recente acties onderin staan;
- een klik op een dashboardtegel opent een consistente drill-down met meer detail;
- een afzonderlijke staaf in een dashboardgrafiek is eveneens klikbaar/tikbaar en opent een drill-down die uitsluitend de bonnen, artikelen, winkels of verwachte herhalingskopen van precies die staafperiode en die reeks toont;
- de twee **Uitgaven**-grafieken stapelen elke staaf op basis van **GS1 GPC-familie**: maximaal vijf grootste productfamilies krijgen een eigen segment, kleinere families worden samengevoegd tot **Overig** en ontbrekende classificaties vallen onder **Niet ingedeeld**;
- ieder gestapeld segment is afzonderlijk klikbaar/tikbaar en filtert de staafdrill-down verder tot alleen die GPC-familie, **Overig** of **Niet ingedeeld**;
- de brede **Uitgaven**-drill-down toont daarnaast een zichtbaar blok **Per categorie** met dezelfde top-5/Overig/Niet-ingedeeld-logica, inclusief een gestapelde balk, bedragen en procentuele verdeling;
- vanuit een dashboarddrill-down opent **Open kassabon** altijd de bestaande mobiele **Kassa → Bonnen**-context en nooit de camerascan als eerste scherm;
- segmentbedragen worden per bon proportioneel aan de productregels aan het bonbedrag gekoppeld, zodat gestapelde segmenten samen exact het uitgavenbedrag van de staaf blijven vormen;
- bij vergelijkingsgrafieken blijft onderscheid bestaan tussen de huidige staaf en de lichtgroene vergelijkingsstaaf; de drill-down volgt exact de aangeklikte reeks;
- de dashboardtegels gebruiken de centrale primaire kleur, witte surfaces, `--radius-md` en uitsluitend de twee centrale tekstgroottes;
- de landingspagina toont niet daarnaast opnieuw grote actiekaarten voor Voorraad, Boodschappen, Kassa, Uitpakken, Catalogus en andere hoofdmodules;
- Gebruiker, Beheerder en Frontteamlid gebruiken hetzelfde huishoud-dashboard; Frontteamfunctionaliteit blijft aanvullend via de centrale navigatie beschikbaar;
- Superuser gebruikt het bestaande Superuser-beheercentrum als eigen dashboardingang;
- gebruikerszichtbare huishoudrollen heten **Gebruiker** en **Beheerder**; legacy technische role keys mogen intern blijven bestaan;
- Superuser, Platformbeheerder en IP-eigenaar blijven drie onderscheiden gebruikerszichtbare platformrollen: Superuser voor functioneel platformbeheer, Platformbeheerder voor technisch beheer/support en IP-eigenaar als beschermde hoogste bevoegdheid met beide sets plus speciaal rollenbeheer.

## Catalogus GPC-hiërarchie vanaf 3 oktober 2026

Voor de artikelcatalogus geldt:

- ieder catalogusartikel krijgt waar nog geen Brick is vastgelegd automatisch een best passende Brick uit de bestaande Nederlandse GS1 GPC-referentielijst; een bestaande handmatige/bevestigde Brick wordt nooit overschreven;
- vanuit die Brick toont ieder catalogusartikel automatisch de bijbehorende **GPC-familie**;
- de familie wordt niet handmatig dubbel opgeslagen maar afgeleid uit de centrale GS1-hiërarchie **Brick → Class/Groep → Family**; daardoor geldt dezelfde logica direct voor bestaande én nieuw geclassificeerde catalogusartikelen;
- de desktop-Catalogus toont **GPC-familie** als afzonderlijke sorteerbare en filterbare kolom en neemt de familie mee in export;
- de mobiele Catalogus en het Catalogusdetail tonen eveneens de GPC-familie;
- **Niet geclassificeerd** is alleen toegestaan als de Nederlandse referentielijst geen bruikbare kandidaat voor het artikel oplevert; dit wordt als uitzonderings-/datakwaliteitsgeval behandeld en mag niet de normale toestand van bestaande Catalogusartikelen zijn;
- gebruikerszichtbare GPC-labels voor **Brick**, **GPC-groep/Class**, **GPC-familie** en Segment komen uitsluitend uit de officiële Nederlandse GS1 GPC-publicatie;
- een Engelstalige naam is geen toegestane gebruikerszichtbare fallback; ontbreekt een Nederlands label lokaal, dan geldt dat als een onvolledige GS1-import/referentiedatafout die moet worden hersteld.

## Nederlandse GPC-hiërarchie in artikeloverzichten vanaf 3 oktober 2026

Voor **Catalogus, Voorraad, Bijna op en Boodschappen** geldt één centrale GPC-weergaveregel:

- GPC-identiteit wordt uitsluitend afgeleid via de canonieke productkoppeling: huishoudartikel → `global_product_id` → bestaande of automatisch afgeleide GPC Brick → `gpc_product_groups`;
- gebruikerszichtbare namen komen uit de bestaande Nederlandse GS1-referentielijst met `language_code = nl`;
- waar een canonieke productkoppeling bestaat, worden **Brick**, **GPC-groep/Class** en **GPC-familie** direct geprojecteerd voor zowel bestaande als nieuw toegevoegde artikelen; er is geen eenmalige artikelmigratie nodig;
- **Voorraad**, **Bijna op** en **Boodschappen** tonen de Nederlandse GPC-hiërarchie als artikelmetadata; desktopoverzichten ondersteunen zoeken/filteren op die GPC-tekst;
- de Catalogus blijft de centrale bron voor de GPC-classificatie en toont in elk geval de Nederlandse Brick/Producttype- en Familienaam; detail/classificatie toont de volledige hiërarchie;
- een puur lokale handmatige boodschappenregel zonder koppeling aan een huishoudartikel of Catalogusproduct krijgt niet op basis van alleen de artikelnaam een GPC-code toegewezen; naamgokken is niet toegestaan. Zodra zo'n regel canoniek wordt gekoppeld, verschijnt de Nederlandse GPC-hiërarchie automatisch;
- Engelse GPC-labels worden niet als gebruikerszichtbare fallback gebruikt.

## Mobiele Boodschappen-interactie vanaf 3 oktober 2026

Voor het mobiele scherm **Boodschappen** geldt aanvullend:

- een tik op een artikel onder **Nog te kopen** verplaatst het direct naar **In winkelwagen**;
- een tik op een artikel in **In winkelwagen** verplaatst het direct terug naar **Nog te kopen**;
- de eerdere selectiecheckboxen en bulkknoppen voor verplaatsen/verwijderen vervallen;
- iedere artikelrij toont rechts na `-` / aantal / `+` een afzonderlijke prullenbakknop;
- de prullenbakknop heeft dezelfde compacte breedte en dezelfde touchhoogte als de min- en plusknop en verwijdert alleen die artikelregel; het pictogram zelf is circa 25% groter dan de eerste implementatie zodat het duidelijk herkenbaar is;
- min, aantal, plus en prullenbak activeren niet per ongeluk de rijverplaatsing;
- als **In winkelwagen** leeg is, wordt onder de sectiekop geen extra leegtekst gerenderd; alleen de kop en teller 0 blijven zichtbaar;
- bij **Artikel toevoegen** verschijnt tijdens zoeken geen inline tekst **Zoeken…**;
- zoekresultaten worden als een zwevende **dropdown/overlay** direct onder het zoekveld getoond en nemen geen extra verticale ruimte in de schermflow in;
- een klik/tik op een bestaand zoekresultaat geldt direct als toevoegen; een aparte vaste knop **Toevoegen** wordt niet getoond;
- als de zoekactie geen kandidaat oplevert, verschijnt in dezelfde dropdown altijd de optie **Toevoegen: [ingevoerde tekst]** om het artikel uitsluitend aan de lokale boodschappenlijst toe te voegen;
- handmatige vrije invoer zonder zoekresultaat kan daarnaast met Enter worden toegevoegd.
- de actie **Boodschappen afgerond** staat rechtsonder onder de sectie **In winkelwagen**, na lijst en paginering, met duidelijke verticale tussenruimte zodat de knop niet tegen de lijst aansluit;


## Superuser-override mobiele actiebalk vanaf 7 oktober 2026

De Superuser kan platformbreed de mobiele actiebalk tijdelijk vastzetten via de instelling **Actiebalk vastzetten (Ja/Nee)** onder **Superuser → Actieknoppen**.

- standaardwaarde voor deze wijziging is **Ja**;
- bij **Ja** staan de vier primaire procesacties in deze vaste volgorde direct op de mobiele actiebalk: **Winkelen**, **Kassa**, **Uitpakken**, **Voorraad**;
- **Meer** blijft als vijfde bediening beschikbaar en bevat alle overige beschikbare hoofdfuncties;
- de vaste selectie vervangt zolang de instelling op Ja staat de normale selectie op basis van recente acties en de eerdere verplichte directe positie van **Bijna op**;
- bestaande routeautorisatie, rollen, permissies en functionele beschikbaarheid blijven leidend; de override verleent geen extra rechten;
- bij **Nee** gebruikt de mobiele actiebalk opnieuw de bestaande dynamische/recent-gebruikte selectie.

## Mobiele paginering en onderste actiebalk vanaf 5 oktober 2026

Voor mobiele viewports van maximaal 720 px gelden aanvullend de volgende app-brede presentatieafspraken:

- tabellen, kaartreeksen en andere gegevenslijsten tonen per pagina maximaal **10 voorkomens**;
- gedeelde mobiele lijsten gebruiken de centrale pagineringscomponent; schermspecifieke paginering wordt alleen behouden wanneer de backend al server-side pagina's van maximaal 10 levert, zoals de Catalogus;
- `MobilePagination` (`src/ui/MobilePagination.jsx`) is de canonieke centrale component voor mobiele paginering van reeksen en lijsten; nieuwe feature-specifieke mobiele paginering is niet toegestaan wanneer dit component volstaat;
- de regel geldt onder meer voor Voorraad, Catalogus, Bijna op, Boodschappen, Meldingen, Kassa en Uitpakken, inclusief bon- en bonregellijsten;
- paginering verandert uitsluitend de presentatie van de reeds beschikbare gegevens en geen autorisatie-, selectie-, filter-, sorteer- of domeinregels;
- de vaste onderste actiebalk toont bij de vier directe acties alleen het bestaande actie-icoon; uitsluitend **Meer** behoudt zichtbare tekst;
- de directe actie-iconen zijn **44 x 44 px**; dit is tweemaal de eerdere 22 x 22 px icoonmaat en verandert de centrale 14/16px teksttypografie niet;
- de mobiele content reserveert voldoende onderruimte voor de grotere vaste actiebalk zodat lijstinhoud, overlays en feedback niet achter de navigatie verdwijnen.

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


## Platformbrede primaire Inhuis-kleur vanaf 5 oktober 2026

De primaire Inhuis-kleur is een **platformbrede functionele weergave-instelling** en geen persoonlijke apparaatvoorkeur.

- de standaardkleur blijft `#005F6A`;
- alleen een bevoegde **Superuser** kan de primaire kleur wijzigen of naar de standaard terugzetten;
- de ingestelde kleur geldt voor alle gebruikers en apparaten via de centrale primaire kleurtokens en wordt bij het laden centraal toegepast;
- een aangepaste kleur moet voldoende contrast met witte tekst behouden; minimaal WCAG-contrastverhouding 4,5:1;
- gewone huishoudinstellingen tonen geen eigen primaire-kleurkiezer;
- deze platforminstelling wijzigt geen autorisatie-, huishoud- of functionele domeingrenzen.

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
- op **lichtgroene knoppen of lichtgroene interactieve knoptoestanden** is de tekst/iconkleur altijd de centrale donkergroene primaire kleur; witte tekst is daar niet toegestaan;
- witte knoptekst is alleen voor voldoende donkere primaire surfaces bedoeld;
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

## Mobiele artikelbeelden en scanner vanaf 2 oktober 2026

Voor artikelpresentatie en mobiel scannen geldt aanvullend:

- de artikelfoto's in lijsten behouden hun bestaande compacte afmetingen; de 40%-vergroting geldt **niet** voor de lijstweergave;
- een beschikbare artikelfoto is overal waar de gedeelde artikelbeeldcomponent wordt gebruikt aanklikbaar en opent een schermvullende overlay; een volgende klik/tap sluit de overlay;
- de foto in die overlay wordt circa **40% groter** weergegeven dan de eerdere overlaypresentatie; de donkere overlayachtergrond en onvervormde beeldverhouding blijven behouden;
- de centrale mobiele **Terug**-knop blijft de enige terugbediening in de app-chrome, is compact en staat links in de header; schermen bouwen geen tweede concurrerende Terug-knop;
- wanneer live barcodecamera in een mobiele browser niet beschikbaar is of faalt, blijft de scanactie herstelbaar via de native camera-/fotokeuze van het apparaat;
- op de mobiele startpagina wordt **Meldingen** niet als extra losse actiekaart gedupliceerd wanneer het aparte meldingenoverzicht bovenaan al doorklikbaar aanwezig is; Meldingen blijft wel beschikbaar voor de centrale onderste actiebalk.

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
- iedere voorraadregel toont voor bevoegde Beheerder direct `−` vóór en `+` na het aantal; `−` boekt exact één eenheid af via de bestaande inventory-eventlogica en `+` verhoogt exact één eenheid via de bestaande handmatige voorraadcorrectie; na iedere mutatie wordt de backendvoorraad opnieuw geladen;
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

### Ondoorzichtige interactieve dialogen — Catalogus fotokeuze, 30 oktober 2026

- Bij een centrale AppFeedback-dialoog met actieknoppen of invoervelden is de dialoogkaart altijd volledig **ondoorzichtig wit**, met donkere leesbare tekst, een subtiele rand, normale binnenruimte en een duidelijke begrenzing.
- De donkere achtergrondlaag dimt de onderliggende pagina, maar teksten, tabellen en kaarten mogen nooit door de dialoogkaart heen zichtbaar blijven. Dit geldt onder meer voor **Productfoto toevoegen** in Catalogus met de acties **Foto maken** en **Foto uploaden**.
- De bestaande centrale AppFeedbackProvider verzorgt deze presentatie op desktop en mobiel; afzonderlijke pagina's leggen geen eigen transparante fotokeuzedialoog over het scherm.
- Dit verandert niet de bestaande snelle, niet-interactieve feedbackbalk en ook niet de opslag- of camera-functionaliteit.

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
- beheer-/ledenlijsten, waaronder **Frontteam beheren**, plaatsen de invoer-/toevoegactie in een afzonderlijk blok boven de tabel en gebruiken daaronder de canonieke `DataTable` met selectiekolom, filterregel, sortering en standaardpaginering; bulkacties staan bij de tabelpaginering en individuele rijactieknoppen worden vermeden wanneer dezelfde actie veilig op een selectie kan worden uitgevoerd;
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

## Dropdowns en keuzelijsten

- alle gebruikerszichtbare keuzelijsten gebruiken de centrale `Select`; er worden geen schermspecifieke korte/lange dropdownvarianten gemaakt;
- op mobiel bestaat de gesloten dropdown uit één veld met de huidige selectie of placeholder plus pijl; bij openen verschijnt altijd hetzelfde overlaypaneel;
- iedere geopende **mobiele** dropdown bevat bovenaan een vast zoekveld **Zoeken…**; typen filtert de opties zonder een ander dropdowntype te openen;
- de geopende lijst staat als portal/overlay boven de bestaande pagina en verandert nooit de hoogte of positie van omliggende content;
- hetzelfde mobiele listbox-patroon geldt ongeacht het aantal opties: maximaal **5 opties** zijn tegelijk zichtbaar; vanaf de zesde optie scrollt uitsluitend de optiesviewport van de dropdown zelf verticaal;
- muiswiel, touch/pan en toetsenbordnavigatie blijven binnen de dropdown werken; de actieve toetsenbordoptie wordt automatisch in beeld gescrold;
- de dropdown reserveert een stabiele scrollbarzone zodat een lange lijst niet ineens een ander breedte-/uitlijningspatroon krijgt;
- de mobiele zoekregel blijft boven de scrollbare opties staan en scrollt dus niet mee;
- alleen de plaatsing boven of onder het veld mag wisselen wanneer de beschikbare viewport dat vereist; de dropdowncomponent en interactie blijven identiek.

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
- desktop `/winkelen` behoudt de bestaande `DataTable`; iedere gebruiker krijgt op `<=720px` de mobiele presentatie, uitsluitend bepaald door de app-brede viewportregel;
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

Het mobiele **Artikel in Voorraad** bouwt visueel voort op de mobiele Voorraadbaseline. Mobiel is een doelgerichte werkweergave en hoeft niet alle desktopinformatie te tonen.

Vaste opbouw:
1. de gedeelde mobiele header **Artikel in Voorraad**;
2. één compacte artikel-/voorraadkaart met foto of **Geen foto**, artikelnaam, artikelgroep/status, actuele locatie en de centrale `QuantityStepper`;
3. direct daaronder één horizontaal scrollbare mobiele tabbalk;
4. de inhoud van precies één actieve tab.

De mobiele hoofdtabbladen zijn:
- **Artikel**;
- **Huishouden**;
- **Identiteit**;
- **Productdata**;
- **Voorraad**;
- **Locaties**, uitsluitend wanneer locatie-ondersteuning actief is.

Er is op mobiel **geen Overzicht-tab met subtabs**. De vier desktop-onderdelen Artikel, Huishouden, Identiteit en Productdata zijn ieder een zelfstandig hoofdtabblad. De bestaande gedeelde artikelcomponenten blijven de inhoudelijke authority, maar hun desktop-subtabbalk wordt in deze mobiele presentatie verborgen.

**Historie** en **Analyse** zijn bewust desktop-only en worden niet als mobiele tabs aangeboden. Dit is een expliciete PO-keuze en geen ontbrekende implementatie.

Mobiele presentatieregels:
- de tabbalk gebruikt compacte pill-tabs zonder desktopachtige knopshadow; actieve tab is duidelijk gemarkeerd en de balk mag horizontaal scrollen;
- velden en acties worden op smalle schermen verticaal gestapeld; horizontaal pagina-scrollen is niet nodig;
- **Voorraad** gebruikt dezelfde bestaande voorraadmutatie-authority als desktop;
- **Locaties** gebruikt dezelfde bestaande locatie-/verplaatsauthority als desktop;
- bij actieve locatie-ondersteuning wordt de actuele locatie ook in de bovenste voorraadkaart getoond;
- voor het **Systeemhuishouden** geldt de systeemcontext als locatie-ondersteunend, ook zonder reguliere `household_product_configuration`;
- **Op boodschappenlijst** blijft als compacte mobiele actie onder de tab **Artikel** beschikbaar;
- terugnavigatie komt uitsluitend uit de gedeelde knop **Terug** van `MobileAppChrome`;
- passieve feedback gebruikt uitsluitend de centrale `AppFeedbackProvider/useAppFeedback`;
- er is geen aparte generieke Opslaan-knop voor het volledige scherm.

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

De applicatiebrede mobiele UI-conformiteitsset omvat **Startpagina, Voorraad, Voorraad-artikeldetail, Bijna op, Boodschappenlijst/Winkelen en Kassa**. Deze schermen staan centraal in één manifest in `frontend/tests/mobile-ui-conformity.contract.mjs`. De gate controleert voor ieder geregistreerd mobiel scherm minimaal de gedeelde `MobileModuleHeader`, uitsluitend de twee centrale lettergroottes `--font-size-ui-body` en `--font-size-ui-title`, en het verbod op alternatieve primaire groentinten. Een bestaand scherm mag niet stilzwijgend uit het manifest verdwijnen.

## Historische styleguidedocumenten

`docs/Rezzerv-Styleguide_v05.08.md` en `Rezzerv-Styleguide_v05.14.md` blijven behouden als audittrail van eerdere PO-besluiten. Hun actuele regels zijn hierboven geconsolideerd. Nieuwe wijzigingen worden niet als nieuwe losse styleguideversies toegevoegd tenzij de PO daar expliciet om vraagt; de canonieke bron wordt direct bijgewerkt.


## Mobiele Kassa

De mobiele **Kassa** is camera-first en gebruikt de bestaande receipt-lifecycle als functionele authority. Desktop Kassa blijft ongewijzigd.

Vaste mobiele flow:
1. **Kassa** opent direct de achtercamera waar browser/permissies dit toelaten;
2. de camerashot wordt via de bestaande bonimport en herkenning verwerkt;
3. **Bon controleren** toont de gestructureerde winkel-, datum-, totaal- en artikelgegevens;
4. **Annuleren** verwijdert uitsluitend de zojuist gemaakte scan en keert terug naar cameramodus;
5. **Opslaan** bewaart de scan en opent **Bonnen**;
6. **Bonnen** is het mobiele detailscherm met opgeslagen kassabonnen en een actie **Nieuwe scan**;
7. **Kassabon** biedt correctie van bongegevens en **Bon bevestigen** gebruikt de bestaande approve-/voorraadketen.

Presentatieregels:
- de mobiele modulekop gebruikt `MobileModuleHeader`; globale terugnavigatie blijft uitsluitend de centrale **Terug**-bediening;
- lokale toestandnavigatie gebruikt geen labels **Terug naar ...**; vanuit Kassabon heet de lokale actie **Bonnen**;
- cameraweergave is dominant; administratieve bonhistorie staat niet op het camerascherm;
- wanneer directe `getUserMedia`-toegang ontbreekt of wordt geweigerd, blijft native camera/file-capture beschikbaar als fallback;
- de gestructureerde bonweergave gebruikt 14/16px typografie en de centrale primaire Inhuis-kleur; feature-CSS introduceert geen alternatieve primaire kleur;
- mobiel wijzigt alleen de presentatie en bediening, niet de receipt-, Uitpakken- of Voorraad-authority.

## Mobiele componenthergebruik (bindend)

- Mobiele schermen met artikelregels gebruiken `frontend/src/ui/MobileArticleRow.jsx`; Voorraad is de visuele referentie. Geen feature-specifieke kopie van dezelfde rijstructuur.
- Aantalbediening gebruikt `frontend/src/ui/QuantityStepper.jsx` wanneer min/plus nodig is.
- Mobiele modulekoppen gebruiken `frontend/src/ui/MobileModuleHeader.jsx` en de globale Terug-bediening uit `MobileAppChrome`; featurepagina's implementeren geen eigen sticky Terug-knop.
- Een afwijkende artikelregel of moduleheader vereist een expliciet functioneel verschil en een contracttest die die afwijking motiveert.
- Nieuwe mobiele modules controleren eerst de centrale UI-componentcatalogus voordat feature-specifieke markup of CSS wordt toegevoegd.


## Mobiele Startpagina — persoonlijke snelstart

De mobiele **Startpagina** is vanaf 26 september 2026 een persoonlijke snelstart en gebruikt op `<=720px` een eigen mobiele presentatie; desktop blijft de bestaande Startpagina gebruiken.

Vaste regels:
- de gedeelde donkergroene `MobileModuleHeader` met titel **Startpagina** staat altijd bovenaan; de globale **Terug**-knop uit `MobileAppChrome` staat op exact dezelfde vaste positie als op alle andere beveiligde mobiele schermen en de titel sluit daarop aan met de reguliere gedeelde headerafstand;
- alle reguliere tekst op de mobiele Startpagina gebruikt uitsluitend de twee centrale groottes `--font-size-ui-body` en `--font-size-ui-title`; het InHuis-woordmerk mag qua lettervorm afwijken, niet qua grootte;
- bovenaan staat één begroeting **Welkom <voornaam> InHuis**; er staat geen tweede InHuis-logo of huis-icoon op de Startpagina;
- het woordmerk is tekstueel **InHuis**: **In** in een schuin geschreven accentvorm in `#28a99e`, **Huis** direct aansluitend in de centrale donkergroene kleur; dak-, blad- en losse decoratieve streepjes zijn niet toegestaan;
- het woordmerk is de enige expliciete typografische uitzondering op Arial; overige gebruikerszichtbare tekst blijft de centrale 14/16px-typografie volgen;
- een compacte meldingenkaart toont het actuele aantal open gebruikersmeldingen wanneer dit beschikbaar is en opent de centrale route **Meldingen**; toekomstige applicatiemeldingen sluiten op dezelfde centrale meldingenervaring aan en vormen geen tweede losse inbox op de Startpagina;
- de eerste vier persoonlijke acties worden als grote snelstartregels getoond; resterende beschikbare acties staan compact onder **Meer acties**;
- **Aanpassen** opent een mobiele ordeningsweergave waarin de gebruiker acties omhoog/omlaag kan plaatsen; de persoonlijke volgorde wordt per gebruiker op het apparaat bewaard en bij een volgende lokale sessie opnieuw toegepast;
- globale platformbeschikbaarheid, autorisatie en featureflags blijven leidend: persoonlijk ordenen kan een niet-beschikbare actie nooit zichtbaar maken;
- de vaste globale mobiele bottom navigation blijft onderdeel van `MobileAppChrome` en staat los van de persoonlijke snelstartvolgorde;
- de Startpagina toont dezelfde globale **Terug**-knop uit `MobileAppChrome` als alle andere beveiligde mobiele schermen; er is geen lokale Startpagina-variant van deze knop.


### Mobiele InHuis-header en persoonlijke Startpagina
- Iedere mobiele moduleheader gebruikt het gedeelde InHuis-woordmerk: turquoise `In` en wit `Huis` op de centrale donkergroene header.
- De mobiele Startpagina toont geen huishoudnaam boven de begroeting; de persoonlijke begroeting is `Welkom <voornaam> InHuis`.
- Primaire actie-iconen zijn groter dan de standaard body-iconen en mogen per actie een eigen zachte accentkleur hebben; dit verandert de centrale primaire UI-kleur niet.
- De regel onder de begroeting is platformbreed configureerbare content en wordt beheerd bij Superuser > Actieknoppen; de standaardtekst is `Fijn dat je er weer bent.`.


## Mobiele Meldingen — geïntegreerde inbox

- De mobiele route **Meldingen** gebruikt de gedeelde `MobileModuleHeader`, globale **Terug**-bediening en globale bottom navigation.
- De inbox combineert menselijke **Berichten** met door **Inhuis** gegenereerde applicatiemeldingen in één chronologische lijst.
- De vaste filters zijn **Alles**, **Berichten** en **Inhuis**; **Alles** is standaard.
- Menselijke communicatie blijft een supportgesprek met onderwerp, status en antwoordmogelijkheid; applicatiemeldingen openen via een deeplink het relevante onderdeel.
- Applicatiemeldingen gebruiken naast tekst een semantische linkerrand: rood actie nodig, oranje aandacht, groen succesvol en blauw informatief. Kleur is nooit de enige informatiedrager.
- Ongelezen applicatiemeldingen krijgen een zichtbare stip en een persistente server-side gelezenstatus.
- Reguliere mobiele typografie blijft beperkt tot `--font-size-ui-body` en `--font-size-ui-title`.
- Een lege inbox toont **Geen nieuwe meldingen** en **Alles is op dit moment bijgewerkt.**


## App-brede knopvorm

- Gewone interactieve knoppen hebben op desktop en mobiel één centrale geometrie: `border-radius: var(--radius-md)` (momenteel 6px).
- Schermen en features mogen geen eigen pilvormige of volledig ronde knopgeometrie afdwingen.
- `frontend/tests/button-shape-global.contract.mjs` bewaakt deze authority bronbreed en draait als onderdeel van de volledige frontendregressie.


## Mobiele Terug-knop en select-typografie

- De globale mobiele Terug-knop blijft visueel binnen de sticky headerbalk en gebruikt overal dezelfde positie en geometrie.
- Op de mobiele Startpagina vraagt Terug expliciet om **Uitloggen** of **Annuleren**; er vindt geen stille browsernavigatie plaats.
- Native `select`-velden gebruiken app-breed `var(--font-family-base)` en `var(--font-size-ui-body)`; schermen mogen geen browserafhankelijke grotere select-typografie introduceren.
- Een bericht aan de Superuser is een Frontteamfunctie: niet-Frontteamgebruikers krijgen geen verzendactie in de UI en de backend weigert directe verzend- of antwoordaanroepen.


## Inlogscherm — gedeelde desktop- en mobiele login

De loginroute gebruikt op desktop en mobiel dezelfde functionele loginform en dezelfde Inhuis-identiteit; viewportwissels mogen de invoervelden of primaire loginactie nooit verbergen.

Vaste regels:
- het vrijstaande woordmerk toont een lichtgroene `In` en `Huis` in de centrale primaire Inhuis-kleur; achter het woordmerk staat geen afzonderlijk groen logoblok;
- er staat geen afzonderlijke paginakop **Welkom**; het loginformulier sluit direct onder het vrijstaande InHuis-woordmerk aan;
- e-mailadres en wachtwoord blijven op iedere viewport zichtbaar, bruikbaar en gekoppeld aan dezelfde authenticatielogica;
- het wachtwoordveld gebruikt een oogbediening in het veld voor tonen/verbergen;
- de primaire **Inloggen**-knop gebruikt de centrale primaire UI-kleur en de app-brede knopradius `var(--radius-md)`;
- de zachte crème/groene achtergrond, decoratieve golven en bladaccenten zijn presentatielaag en veranderen geen login-, sessie- of autorisatiegedrag;
- desktop behoudt de reguliere applicatieheader; mobiel gebruikt de compacte loginpresentatie zonder die desktopheader.


### Platformbrede achtergrond van het inlogscherm

- De Superuser kan onder **Inlogscherm** één JPG/JPEG als platformbrede loginachtergrond instellen.
- De ingestelde afbeelding geldt voor alle gebruikers en voor zowel desktop als mobiel; loginstate en authenticatie blijven één gedeelde flow.
- Alleen de platform-Superuser mag de afbeelding vervangen of de standaardachtergrond herstellen; het uitlezen van de actieve achtergrond is vóór authenticatie beschikbaar omdat het inlogscherm publiek is.
- Uploads zijn beperkt tot geldige JPG/JPEG-bestanden van maximaal 8 MB en worden ook server-side gevalideerd.
- De afbeelding wordt gecentreerd over de volledige beschikbare schermhoogte weergegeven met behoud van de oorspronkelijke beeldverhouding; de breedte schaalt automatisch mee en mag bij een smalle viewport buiten beeld vallen.
- Op mobiel is de login-card bewust compacter en smaller, met verkleinde verticale tussenruimtes en bediening, zodat meer van de ingestelde achtergrond zichtbaar blijft zonder loginfunctionaliteit te verwijderen.
- Zonder aangepaste JPG blijft de ingebouwde standaardachtergrond actief.

## App-brede letterkleurnorm vanaf 28 september 2026

Voor gebruikerszichtbare tekst gebruikt Inhuis uitsluitend:

- **zwart (`#000000`)** voor gewone tekst, labels, toelichtingen en waarden;
- **Inhuis-donkergroen (`#005F6A`)** voor links, acties en semantische status-/waarschuwings-/fouttekst.

Rode, oranje, blauwe, paarse of grijze letterkleuren zijn niet toegestaan. Achtergrond-, rand-, grafiek- en decoratieve iconenkleuren vallen niet onder deze letterkleurnorm. **Wit (`#FFFFFF`)** is verplicht als contrastkleur op ieder canoniek donkergroen UI-vlak (`#005F6A`), waaronder headers, primaire acties, groene tabelheaders en de sorteerbediening daarin. Zwarte of donkergroene letters op zulke donkergroene vlakken zijn niet toegestaan.


## Mobiele Catalogus — overzicht en detail

De mobiele **Catalogus** gebruikt op `<=720px` een eigen Inhuis-presentatie; de bestaande desktop-tabel en desktop-detailweergave blijven ongewijzigd. Overzicht en detail vormen daarbij één mobiele Catalogus-flow met dezelfde gedeelde presentatie-authority.

Vaste regels:
- overzicht en detail gebruiken de gedeelde `MobileModuleHeader`, de globale mobiele navigatie en de groene Inhuis-achtergrond;
- het overzicht toont zoeken, soortfilter, A–Z/Z–A-sortering en compacte productregels met foto; een productregel opent het catalogusdetail;
- het mobiele detail toont productsamenvatting, GPC-classificatie, identiteiten, gekoppelde huishoudartikelen en kassabonregels als leesbare mobiele secties in plaats van brede tabellen;
- productfoto uploaden/camera en bestaande GPC-bevoegdheden blijven functioneel gelijk aan desktop;
- reguliere tekst gebruikt uitsluitend de centrale body-/titelgroottes en de app-brede zwart/donkergroen-letterkleurnorm;
- mobiel verandert uitsluitend presentatie en bediening; catalogus-, autorisatie- en classificatie-authority blijven gedeeld met desktop.

## Installeerbare mobiele Inhuis-app (PWA)

Inhuis kan vanuit een ondersteunde mobiele browser als standalone web-app worden geïnstalleerd wanneer de runtime via HTTPS wordt aangeboden.

Vaste regels:
- het web-appmanifest gebruikt de gebruikerszichtbare naam **Inhuis**, start op `/` en gebruikt `display: standalone`;
- de installatieset bevat expliciete app-iconen voor minimaal **192x192** en **512x512**;
- het app-icoon gebruikt de centrale Inhuis-donkergroene achtergrond `#005F6A`, het witte huis/winkelmand-beeldmerk en het woordmerk **InHuis** met turquoise `In` (`#28A99E`) en witte `Huis`;
- de PWA-themakleur volgt de centrale primaire Inhuis-kleur `#005F6A`;
- installatie verandert geen authenticatie-, autorisatie-, data- of backendcontract; de geïnstalleerde app gebruikt dezelfde beveiligde webapp en API-routes.


### Mobiel Uitpakken vanaf 28 september 2026
- Uitpakken gebruikt op mobiel dezelfde compacte lijsttaal als Voorraad en Boodschappen: canonieke groene moduleheader, zoek/filterstrook, witte kaartregels en minimaal 44 px touchdoelen.
- Een kassabonregel toont selectie, winkel, datum, aantal artikelen en status; openen gebeurt via de regel/chevron.
- Bulkacties blijven beschikbaar zonder de lijstbreedte op mobiel te vergroten; detailinhoud blijft functioneel bereikbaar onder het overzicht.


### Toegankelijke tekstgrootte vanaf 28 september 2026
- InHuis gebruikt app-breed twee semantische lettergroottes: gewone UI-tekst en titels.
- De gebruiker kan onder Instellingen > Weergave kiezen uit Standaard, Groot en Extra groot; de keuze geldt op het huidige apparaat en wordt direct app-breed toegepast.
- Schermen en componenten gebruiken uitsluitend de centrale `--font-size-ui-body` en `--font-size-ui-title` tokens voor de genormeerde UI-typografie, zodat toegankelijk vergroten de onderlinge hiërarchie behoudt.
- Browser- en systeemzoom mogen niet worden geblokkeerd en blijven aanvullend beschikbaar.


### Mobiele Kassa — gedeelde accentkleur en kassabondetail (29 september 2026)

- Selectievakjes bij bonregels en bulkselectie gebruiken `accent-color: var(--color-mobile-ui-primary)`; een hard gecodeerde primaire hexkleur is niet toegestaan, zodat de persoonlijke Weergave-instelling ook hier doorwerkt.
- De mobiele kassabon toont uitsluitend de tabs **Bonregels** en **Bonkop**. De bestaande desktop-Kassa behoudt daarnaast **Bron**.
- De mobiele camera-, bestandsupload-, boncorrectie- en goedkeuracties gebruiken de bestaande centrale knop- en overlaycomponenten. De mobiele totalencontrole blijft onderdeel van het kassabondetail.
- Live camerabegeleiding in Kassa, waaronder de AI-bonranddetectielabels en camerahints, gebruikt uitsluitend `--font-size-ui-body`; feature-CSS introduceert hiervoor geen lokale 12px/13px-lettergrootte.


### Mobiel hoofdlocaties toevoegen in Instellingen (29 september 2026)

- Op viewports van maximaal 720 px staat boven de hoofdlocatietabel een compact invoerformulier met het label **Nieuwe hoofdlocatie**, een volledig breed naamveld en de centrale knop **Locatie toevoegen**.
- Boven 720 px blijft de bestaande desktopinvoerrij onder de hoofdlocatietabel zichtbaar; het mobiele formulier is daar verborgen. Beide varianten gebruiken dezelfde bestaande validatie, autorisatie, API en centrale overlaymeldingen.
- De mobiele formulierbreedte volgt de beschikbare viewport zonder horizontale verschuiving; de tabel blijft indien nodig binnen de eigen container horizontaal scrollbaar.


### Mobiel Uitpakken — locatie direct vanuit een bonartikel aanmaken (29 september 2026)

- De locatiekiezer behoudt ook op mobiel de twee kolommen **Locatie** en **Sublocatie** naast elkaar, met de acties **+ Nieuwe locatie** en **+ Nieuwe sublocatie** direct onder de bijbehorende keuzelijsten voor een bevoegde huishoudadmin. Er komt geen extra knop boven de lijsten.
- Het bestaande inline aanmaakformulier gebruikt de bestaande autorisatie en API. Bij exacte locatie-inrichting leidt een nieuw aangemaakte hoofdlocatie direct door naar het aanmaken van een sublocatie; alleen een complete locatie/sublocatie wordt als artikelbestemming geselecteerd.


### Uitpakken → Locatiebeheer → Uitpakken (29 september 2026)

- Vanuit de bonregel kan een bevoegde huishoudadmin naar **Instellingen → Locaties** navigeren, met behoud van de bonartikelcontext. De locatiekiezer zelf bevat geen knop **Beheer locaties**.
- Bij exacte locatie-inrichting volgt na het toevoegen van een hoofdlocatie de sublocatie. Na opslaan keert Inhuis terug naar het bonartikel en neemt de volledige locatie/sublocatie over, met behoud van bestaande keuzes rond artikelstandaardlocaties.
- De actie **Terug naar Uitpakken** keert terug zonder nieuwe bestemming.

- In de mobiele kassabon is de route naar Locatiebeheer ook **direct onder de locatiekeuze van elke open bonregel** zichtbaar; niet verborgen in een dropdownoptie. De bestaande desktop-locatiekiezer blijft intact.

- In de locatiekiezer heet de afsluitknop **Overnemen** in plaats van **Sluiten**; de bestaande directe selectie van locatie/sublocatie blijft behouden.

### Uitpakken — locatiekiezer: zoeken en actierij (29 september 2026)

- Het gedeelde zoekveld doorzoekt op mobiel en desktop zowel de naam van de hoofdlocatie als de namen van haar sublocaties. Een sublocatiematch toont de bijbehorende hoofdlocatie en de overeenkomende sublocaties; een hoofdlocatiematch toont haar sublocaties.
- De onderste acties **Standaard locatie**, **Verwijderen** en **Overnemen** vullen, wanneer alle drie zichtbaar zijn, elk een gelijk derde van de beschikbare overlaybreedte. De bestaande twee kolommen voor locatie en sublocatie blijven intact.

### Compacte aantalknoppen Voorraad en Boodschappen (29 september 2026)

- Uitsluitend op de mobiele overzichtsregels van Voorraad en Boodschappen is de combinatie **− / aantal / +** circa 30% smaller; de gedeelde QuantityStepper behoudt elders zijn bestaande afmetingen.
- De knophoogte en veldhoogte blijven 44 px, de app-brede lettergroottes blijven ongewijzigd. Het bewerkbare aantal in Voorraad blijft rechtstreeks via het numerieke toetsenbord aanpasbaar.

## Mobiele detailnavigatie vanaf 29 september 2026

Op alle mobiele lijst- en instellingenschermen met een detailroute wordt de volledige detailrij zelf gebruikt om het detail te openen. Een losse `>`/`›`-chevron of aparte detailknop aan het einde van de rij is overbodig en wordt niet getoond. Bestaande bediening in de rij (checkbox, aantalknoppen en invoervelden) blijft onafhankelijk werken; desktopweergave blijft ongewijzigd.


## Boodschappen — persoonlijke zoekwijze

- Het zoekblok **Artikel toevoegen** toont op desktop en mobiel de filter **Zoekwijze** met **Specifiek** en **Generiek**.
- **Specifiek** is standaard en is bedoeld voor concrete artikelen met de grootste kans op productidentiteit en productfoto; **Generiek** is bedoeld voor Producttypen en Artikelgroepen.
- De zoekwijze is een persoonlijke gebruikersvoorkeur en mag niet huishoudbreed voor andere gebruikers worden overschreven.
- De bestaande centrale kandidaatpresentatie (`SearchCandidateList`) en maximumregel van vijf kandidaten blijven ongewijzigd van kracht.


### Boodschappen — selectie en winkelwagen (30 september 2026)

- In het blok **Artikel toevoegen** staat het zoekveld boven **Zoekwijze**.
- **Zoekwijze** gebruikt de centrale `Select`; trigger, lijst en opties volgen `var(--font-size-ui-body)` en daarmee de app-brede instelling Standaard/Groot/Extra groot.
- De checkbox vóór een mobiele boodschappenregel is een selectiecheckbox voor bulkacties en verandert nooit rechtstreeks de koopstatus.
- **Nog te kopen** staat altijd boven **In winkelwagen**; beide secties blijven tegelijk zichtbaar.
- Geselecteerde regels onder **Nog te kopen** bieden **Verwijderen** en **In winkelwagen**; geselecteerde regels onder **In winkelwagen** bieden **Verwijderen** en **Terug naar nog te kopen**.
- De artikelregel blijft één compacte `MobileArticleRow` met foto, artikelnaam en de bestaande compacte `QuantityStepper`.

## Mobiele Incidentele aankoop (1 oktober 2026)

- De route **Incidentele aankoop toevoegen** gebruikt op viewports van maximaal 720 px een eigen mobiele presentatie; de bestaande desktopweergave blijft boven 720 px ongewijzigd.
- De mobiele pagina gebruikt `MobileModuleHeader` met titel **Incidentele aankoop**, de globale **Terug**-bediening en de centrale mobiele bottom navigation uit `MobileAppChrome`.
- **Barcode scannen** is de primaire mobiele ingang. Na herkenning sluit de camera-overlay en wordt het bestaande barcode-opzoekpad gebruikt om artikelgegevens waar mogelijk aan te vullen.
- Het mobiele formulier staat in één kolom en gebruikt in deze volgorde: Barcode, Artikelnaam, Artikelnummer, Aantal, Aankoopdatum, Locatie, Sublocatie, Winkel / platform, Prijs en Notitie.
- Voor locatiekeuze worden op mobiel uitsluitend hoofdlocaties aangeboden waarvoor ten minste één actieve sublocatie beschikbaar is; locatie en sublocatie gebruiken de centrale `Select`.
- Wanneer geen complete locatie/sublocatiecombinatie beschikbaar is, toont de pagina de actie **Locatie toevoegen** naar **Instellingen → Locaties**.
- Passieve barcode-, validatie- en opslagfeedback gebruikt op mobiel uitsluitend `AppFeedbackProvider/useAppFeedback` en verschuift de formulierinhoud niet.
- Onderaan staan mobiel uitsluitend **Leegmaken** en **Opslaan**. Een aparte knop **Annuleren** wordt niet getoond omdat de globale mobiele **Terug**-bediening die navigatiefunctie vervult.
- Na succesvol opslaan blijft het bestaande gedrag gelden: de aankoop wordt aan Voorraad toegevoegd en de gebruiker keert terug naar **Voorraad**.
- Mobiele invoervelden en acties hebben minimaal circa 44 px touchhoogte, gebruiken uitsluitend de centrale body-/titeltypografie en volgen de app-brede primaire kleur en knopgeometrie.


## Mobiel dashboardstatus vanaf 6 oktober 2026

- De mobiele dashboardstatus gebruikt vijf directe statusknoppen: **Meldingen**, **Boodschappen**, **Bonnen open**, **Bonnen downloaden** en **Bijna op**.
- **Bonnen open** telt unieke kassabonnen die in Kassa of Uitpakken nog niet volledig naar Voorraad zijn verwerkt; bonregels worden niet als afzonderlijke bonnen geteld.
- **Bonnen downloaden** toont uitsluitend een live, objectief bepaalbaar aantal uit persistent gekoppelde winkelaccounts. Browser-assisted koppelingen zonder server-side boninventaris worden niet stil als nul meegeteld.
- **Bijna op** toont het actuele aantal Bijna-op-signalen en opent rechtstreeks de module Bijna op.


## Mobiele actiebalk en Superuser-header vanaf 6 oktober 2026

- De globale mobiele onderste actiebalk bevat geen dubbele acties. **Bijna op** is een vaste beschikbare actie; de overige posities worden uniek aangevuld uit recente beschikbare acties, gevolgd door **Meer**.
- In de mobiele actiebalk gebruikt **Meldingen** een grote cursieve donkergroene letter **i** als informatie-icoon.
- **Voorraad** gebruikt in de mobiele actiebalk een stellingkast met dozen als icoon.
- **Kassa** gebruikt in de mobiele actiebalk een groene betaalpas als icoon.
- **Uitpakken** gebruikt in de mobiele actiebalk een boodschappentas met horizontale kleurstrepen.
- Op de mobiele Superuser-route staat de globale **Terug**-bediening links in een eigen sticky donkergroene headerbalk; zij scrollt niet weg met de pagina-inhoud.


### Mobiele dashboardkleuren en actiebalkiconen — 6 oktober 2026

- De vijf mobiele dashboardstatusknoppen gebruiken lichte pastelachtergronden zodat gewone donkere tekst leesbaar blijft: Meldingen pastelrood, Boodschappen pastelblauw, Bonnen open pastelpaars, Bonnen downloaden pastelgeel en Bijna op pastelbruin.
- De grote cursieve **i** van Meldingen is oranje.
- Bij het icoon **Bijna op** is uitsluitend de neerwaartse pijl oranje; de overige lijnen behouden de reguliere actiebalkkleur.
- Het Voorraad-icoon blijft een stellingkast; de dooscontouren zijn fijner dan de kastlijnen. Rechtsboven en links in het midden staan bewust geen dozen.


### App-brede paginering — 6 oktober 2026

- Alle pagineringscomponenten gebruiken centraal dezelfde bediening: **1**, **−**, **+** en als laatste knop het bekende totale aantal pagina's.
- Alleen wanneer het totale aantal pagina's technisch niet bepaalbaar is, luidt de laatste knop **Einde**.
- Schermen introduceren geen eigen afwijkende labels voor Eerste/Vorige/Volgende/Laatste; de gedeelde `Pagination`-component is hiervoor de UI-authority.


### Mobiele Kassa — directe bonnenlijst en batchgoedkeuring — 6 oktober 2026

- Een deeplink naar **Kassa → Bonnen** initialiseert de mobiele Kassa direct in de bonnenlijst; het camerascherm wordt daarbij niet eerst kort getoond.
- Bij geselecteerde bonnen staat **Goedkeuren** links van **Verwijderen**, met de standaard centrale marge tussen beide acties.
- Batchgoedkeuring hergebruikt per bon de bestaande canonieke receipt-goedkeurroute. Bonnen die niet kunnen worden goedgekeurd blijven geselecteerd en worden expliciet gemeld; geslaagde bonnen gaan volgens de bestaande flow naar Uitpakken.


### Voorraad-hoofdscherm en Kassa-volgorde — 6 oktober 2026

- Het hoofdscherm **Voorraad** toont naast artikelnaam en aantal uitsluitend de gebruikte metadata **Brick**, **Productfamilie**, **Locatie** en **Sublocatie**. Lege locatievelden worden niet als placeholdermetadata getoond.
- **GPC-groep/Class**, Artikelgroep en een tweede productnaam worden niet meer als extra metadata in het Voorraad-hoofdscherm getoond; zij blijven waar van toepassing beschikbaar in detail- of beheercontext.
- De open bonnen in **Kassa** worden op aankoopdatum oplopend weergegeven: de oudste bon staat bovenaan. Bij gelijke of ontbrekende aankoopdatum is aanmaaktijd de stabiele vervolgsortering.


### Huishoudinstelling automatische kassabongoedkeuring — 6 oktober 2026

- **Instellingen → Winkelimport** bevat per huishouden de instelling **Kassabonnen automatisch goedkeuren**; de veilige standaardwaarde is **uit**.
- Alleen een huishoud-**Beheerder** mag deze instelling wijzigen. Een reguliere **Gebruiker** kan de instelling niet aan- of uitzetten; de backend handhaaft dit met dezelfde admin-authority als de overige huishoudbrede Winkelimport-instellingen.
- Wanneer automatische goedkeuring aan staat, mag alleen een technisch complete bon met geldige winkel, aankoopdatum, ten minste één geldige bonregel en sluitende totalen automatisch naar **Uitpakken** gaan. Twijfel of een totalenafwijking blijft fail-closed in **Kassa**.


- De automatische goedkeurpoort hergebruikt exact dezelfde interne receipt-approval authority als handmatig Goedkeuren. Automatisch goedkeuren staat **geen** totalenoverride toe en stopt bij een afgeleide/default aankoopdatum of een winkelnaam die gebruikerscontrole vereist.
- Voor reeds binnengehaalde digitale winkelbonnen wordt de instelling eveneens toegepast voordat de open Kassa-wachtrij wordt getoond, zodat complete bonnen rechtstreeks naar Uitpakken doorstromen.


### Mobiele Boodschappen en Meer-popup — 6 oktober 2026

- **Boodschappen afgerond** staat buiten en direct onder de sectie/tabel **In winkelwagen**, met de standaard tussenruimte.
- De mobiele actie **Meer** opent een modale popup boven de huidige pagina en navigeert niet naar een afzonderlijk Meer-scherm.
- Een keuze uit de popup sluit deze en opent daarna de gekozen functie; tikken buiten de popup of op sluiten laat de huidige pagina intact.


- Het mobiele **Kassa**-icoon is een eenvoudige betaalpas in de centrale groene Inhuis-kleur; het eerdere kassaregister-icoon vervalt.


### Mobiel Uitpakken — Kassabondetail in dezelfde UI-lijn als Kassa — 7 oktober 2026

- Het mobiele Kassabondetail in **Uitpakken** opent direct op **Bonregels**; de desktop-tabs **Bonregels** en **Diagnose** worden op mobiel niet getoond.
- Boven de bonregels staat op mobiel één gecombineerd zoek-/filterveld. Dit veld zoekt over artikeltekst, status en statusreden, mapping, locatie, artikelgroep en de aanduiding dat een regel al naar voorraad is verwerkt.
- De eerdere losse mobiele filters voor status, mapping en locatie en de afzonderlijke actie **Filters wissen** vervallen in dit detail; desktop behoudt zijn bestaande tabel- en filterbediening.
- De bonregels blijven op mobiel als compacte kaart-/lijstweergave met paginering staan, in dezelfde mobiele detailtaal als **Kassa**.
- In het mobiele kassabondetail heeft iedere bonregel een zichtbare actie **Details**. Die opent dezelfde bestaande bonartikeldetailfunctie als desktop, inclusief barcode/GTIN-controle, barcodecamera, universeel artikel en koppelen.
- Een huishoud-Beheerder gebruikt op mobiel dezelfde locatiepicker als desktop en kan daarin inline **+ Nieuwe locatie** en **+ Nieuwe sublocatie** gebruiken; de nieuw aangemaakte keuze wordt via de bestaande flow direct op de bonregel toegepast.
- De actie **Exporteren** wordt in het mobiele Uitpakken-Kassabondetail niet getoond; desktop blijft ongewijzigd.
- De kassabonkop toont mobiel alleen **Winkel · aankoopdatum** als duidelijke donkergroene bloktitel; technische status-, regelaantal- en vereenvoudigingstoelichting wordt daar niet getoond.
- Boven de bonregels staat één checkbox **Alle artikelen** waarmee alle nog niet verwerkte artikelregels van de kassabon in één keer worden geselecteerd, ook wanneer ze over meerdere mobiele pagina's zijn verdeeld.
- De mobiele bulkactie voor locatie heet **Pas standaardlocatie toe**.
- De mobiele samenvattingsregel **Totaal / Klaar / Actie nodig / Al naar voorraad** wordt niet getoond.
- Bonregels die klaar zijn om naar Voorraad te gaan hebben een lichtgroene achtergrond; open bonregels die nog niet klaar zijn hebben een lichtoranje achtergrond; reeds verwerkte regels blijven neutraal en alleen-lezen.
- Autorisaties blijven leidend: een Viewer kan details bekijken maar geen locatie, artikelgroep, barcodekoppeling of voorraadverwerking wijzigen; locatie-aanmaak blijft uitsluitend beschikbaar voor de huishoud-Beheerder; reeds verwerkte regels zijn in detail alleen-lezen.



### Huishoudwisselaar in de header — 7 oktober 2026

- De huishoudwisselaar in de gedeelde header wordt uitsluitend getoond wanneer de backend expliciet `can_switch_households=true` retourneert én er meer dan één beschikbaar regulier huishouden is.
- Bij één huishouden, een niet-reguliere context of een fout bij het ophalen van huishoudens wordt de wisselaar fail-closed niet getoond.
- Deze regel verandert geen styling, maatvoering of design tokens van de header; zij borgt alleen dat de bestaande wisselbediening niet zichtbaar blijft zonder actuele server-side authority.
- De zichtbaarheid van deze bediening is daarmee onderdeel van de gedeelde Header-contractafspraak en mag niet door alleen client-side telling van huishoudens worden afgeleid.


### App-breed mobiel: Exporteren is desktop-only — 7 oktober 2026

- Op de centrale mobiele viewport (`<=720px`) wordt de actie **Exporteren** nergens in Inhuis gebruikerszichtbaar aangeboden, ongeacht module, overzicht of detailscherm.
- Desktopweergaven (`>720px`) behouden bestaande exportfunctionaliteit ongewijzigd.
- Deze app-brede mobiele regel vervangt oudere mobiele afspraken waarin **Exporteren** nog als zichtbare bulk- of detailactie werd genoemd.
- De exportcode hoeft niet per module te worden verwijderd; de gedeelde Button-authority markeert de exacte actie **Exporteren** en de centrale mobiele styling verbergt die uitsluitend op de mobiele viewport.

## Pagina-eigen meldingen bij Winkelkoppelingen — 11 oktober 2026

- Het resultaat van handmatige AH-bonnensynchronisatie wordt op **Winkelkoppelingen** getoond via de bestaande centrale `AppFeedbackProvider` en blijft op die pagina zichtbaar tot de gebruiker de melding sluit of navigeert.
- Bij verlaten van de pagina **Winkelkoppelingen** wordt de bijbehorende AH-synchronisatiemelding direct verwijderd. Een laat binnenkomend resultaat mag die melding niet opnieuw tonen op een andere pagina.
- De eigenaar van de melding wordt onderscheiden met de sleutel `ah-receipt-sync`. De op pagina-verlaten uitgevoerde opruiming mag uitsluitend een melding met deze sleutel wissen, nooit een gelijktijdige melding van een andere module.
- Er is **geen nieuwe modale, kaart-, kleur- of tokenvariant** geïntroduceerd; gebruik en vormgeving volgen volledig de bestaande centrale feedbackstijl.

### Lidl-webimport: paginagebonden feedback en eerlijke verwerkingstelling — 11 oktober 2026

- Lidl-webimportmeldingen gebruiken dezelfde centrale `AppFeedbackProvider` als AH en krijgen een eigen sleutel `lidl-receipt-import`. Bij verlaten van Winkelkoppelingen verdwijnen uitsluitend de Lidl- en AH-pagina-eigen syncmeldingen; meldingen van andere onderdelen blijven intact.
- Ook bij een laat antwoord van de browserbridge na het verlaten van Winkelkoppelingen verschijnt geen nieuwe Lidl-melding op Kassa of elders.
- Een succesvolle serverreactie betekent niet automatisch een nieuwe bon. De Lidl-terugkoppeling onderscheidt **nieuw**, **al bekend**, **bestaande bon bijgewerkt** en **mislukt** aan de hand van het bestaande backend-importresultaat. Een onbekend resultaat telt nooit stilzwijgend als nieuw.
- De melding presenteert alleen aantoonbaar nieuwe bonnen als toegevoegd aan Kassa; bestaande bonnen houden hun bestaande verwerkingstoestand. Er wordt geen nieuw feedbackdesign, kleurpatroon of modale variant geïntroduceerd.

## Mobiele headerbranding en Uitpakken-acties (PR #588)

- De gedeelde mobiele header toont rechts het officiële tweedelige InHuis-woordmerk uit de bestaande inlogpagina (de herkenbare groene cursieve **In** plus **Huis**), op mobiele schaal. Geen los huis-pictogram als vervanging voor de productidentiteit.
- Deze headercorrectie is appbreed: individuele schermen plaatsen geen eigen afwijkend mobiel headerlogo.
- In het mobiele Uitpakken-overzicht staan de bestaande bulkacties **Exporteren** en **Verwijderen** onder de paginering in de normale documentstroom. Het actiegebied is niet sticky/fixed en krijgt geen extra wit paneel, rand of aparte achtergrond.
- Bestaande voorwaarden voor selectie, beschikbaarheid en autorisaties blijven van toepassing.

## Uniforme paginering voor tabellen en lijsten — 15 oktober 2026

Voor alle gebruikerszichtbare tabellen en lange, tabelachtige lijsten op desktop en mobiel geldt de uniforme pagineringsbaseline:

- Per pagina worden maximaal **10 resultaten** getoond, na filtering en sortering over de volledige relevante resultaatset.
- De pagineringsbediening staat **onder** de tabel of lijst in de normale documentstroom en verschijnt uitsluitend wanneer er meer dan 10 resultaten zijn; zij is niet sticky of zwevend.
- Bij wijziging van filters of sortering wordt pagina 1 getoond; na verwijdering of mutatie wordt een inmiddels ongeldige paginapositie naar de laatste bestaande pagina teruggebracht.
- Bestaande geselecteerde records blijven geselecteerd bij wisselen van pagina. Een actie **Alles selecteren** heeft uitsluitend betrekking op de zichtbare records van de huidige pagina; bulkacties respecteren de totale expliciete selectie.
- Dezelfde regels gelden voor eigen tabelimplementaties, de gedeelde `DataTable` en mobiele kaartlijsten; reeds aanwezige paginering wordt hergebruikt en niet gedupliceerd.
- Korte statische navigatiemenu's, formulieren en vaste configuratiekeuzes worden niet kunstmatig gepagineerd.

## Rustige paginawisseling (desktop en mobiel)

Bij een asynchrone paginawisseling blijven de laatst geladen tabelregels of mobiele kaarten zichtbaar totdat de nieuwe set succesvol beschikbaar is (stale-while-revalidate). Alleen de records/kaarten en totalen voor de nieuwe pagina worden daarna tegelijk vervangen. Gebruik een bescheiden voortgangsindicatie zonder lege tussenweergave en blokkeer tijdelijk acties op nog zichtbare regels van de vorige pagina. Bij een eerste bezoek zonder eerdere resultaten blijft de normale laadmelding gelden. Bij wisseling van huishouden, autorisatiescope of andere gevoelige dataset mogen oude records niet zichtbaar blijven. Lokale paginering over al aanwezige gegevens wisselt direct, zonder laadstatus.

## PR #590 — uniforme mobiele tabelselectie en bulkacties (17 oktober 2026)

- **Uitpakken mobiel is de referentie**: de checkbox **Alles** staat bovenaan, rechts uitgelijnd direct boven iedere selecteerbare lijst/tabel. De selectie geldt voor de zichtbare pagina en bewaart een eerder geselecteerde andere pagina waar het scherm die selectie ondersteunt.
- Bulkknoppen staan **rechts onder de tabel en onder de paginering**, in de normale documentstroom (geen sticky of zwevend actieblok). Dit geldt ook wanneer meerdere knoppen over regels moeten afbreken op smalle schermen.
- Gebruik waar toepasselijk de gedeelde CSS-klassen `rz-mobile-table-select-row` en `rz-mobile-table-bulk-actions`, niet per scherm verschillende selectiebalken.
- Toepassing op de mobiele bulkoverzichten Uitpakken (zowel bonnenlijst als bonregels in het detail), Kassa-bonnen, Kassa-bonregels en Bijna op. De bonregels in Uitpakken selecteren met **Alles** alleen de huidige pagina; selectie op andere pagina's blijft intact. Schermen zonder bulkselectie (zoals mobiele Voorraad en Boodschappen) krijgen niet kunstmatig een selectievakje.
- **Bijna op** behoudt de aparte handeling **Verwijderingen ongedaan maken** onder het tabelpaneel op de groene schermachtergrond; deze handeling valt niet onder geselecteerde-rijen-bulkacties.

## PR #590 — compact mobiel Dashboard (17 oktober 2026)

- In de vijf bovenste status-/navigatietegels staat de **telling bovenaan** en de omschrijving **onderaan** in de tegel, gecentreerd; kleuren, tellerbronnen en navigatie blijven gelijk.
- In iedere mobiele dashboardgrafiek staan de **titel links en de bijbehorende waarde rechts op dezelfde eerste regel**. De bestaande toelichting volgt er direct onder in **zwart**. De grafiek zelf en de vier periode-/drilldowncontracten blijven ongewijzigd.
- De gedeelde `mobileHome.css`-grid gebruikt `title value` gevolgd door `detail detail` en `chart chart`. Er wordt geen afzonderlijke mobiele datalogica of tweede bron voor bedragen toegevoegd.

## PR #590 — verdere verdichting mobiel Dashboard (17 oktober 2026)

- Verwijder de **gezamenlijke witte achtergrond en omlijsting** achter de vijf status-tegels en achter de periodeknoppen Dagen/Weken/Maanden. Behoud de vijf afzonderlijke gekleurde klikbare tegels en de zichtbare actieve periodeknop.
- Toon de welkomtekst en de gepersonaliseerde subtitel op dezelfde regel waar voldoende ruimte is; regelomloop blijft mogelijk op smalle mobiele schermen.
- Maak de grafiekkaarten compacter met minder verticale kaartpadding en tussenruimte. Behoud de bestaande grafiekhoogte, aslabels, klikbare staven en toegankelijke focusstijlen: verkleinen mag geen gegevens of assen afsnijden.
- Deze wijziging raakt alleen de mobiele dashboardpresentatie; waarden, periodefilters, grafiekgegevens en drilldowns blijven ongewijzigd.

## PR #591 — heldere huishoudwissel en rustige Kassa-start (18 oktober 2026)

- Keuzevelden en dropdowns in de header tonen **donkergroene tekst op een witte of lichtgroene achtergrond**, of **witte tekst op een donkergroene achtergrond**. Witte tekst op grijs en andere onvoldoende contrasterende combinaties zijn niet toegestaan. Deze norm geldt ook voor de zichtbare opties van de huishoudwisselaar.
- De huishoudwisselaar blijft een bestaande toegankelijke select, met de actuele huishoudnaam, bestaande autorisatievoorwaarden en zichtbare toetsenbordfocus. Er worden geen nieuwe rollen of wisselroutes ingevoerd.
- In Kassa desktop is het paneel met de afbeelding/preview van de kassabon **standaard ingeklapt** bij openen of wisselen van bon. De gebruiker kan het paneel altijd weer uitklappen; de inhoud en bonregels blijven beschikbaar.
- Voorraad presenteert aanwezige artikelregels zodra de primaire voorraadrespons arriveert; optionele artikelgroeplabels mogen later worden aangevuld, zonder wijzigingen van bewerkte artikelwaarden of huishoudencontext.
- De bestaande pagineringsstandaard blijft **10 resultaten per pagina**; een eventuele appbrede wijziging naar 8 vereist een apart expliciet PO-besluit en daarop aansluitende contractaanpassing.

## PR #591 — mobiele kassabonkaarten en uniforme actiebalk (18 oktober 2026)

- De mobiele bonnenlijsten van **Uitpakken** en **Kassa** gebruiken dezelfde compacte kaartstructuur: selectiecheckbox links, winkelnaam bovenaan, daaronder datum en aantal artikelen. De statusnaam wordt **niet als zichtbare tekst** op de kaart herhaald.
- Een bon met de status **Controle nodig** krijgt als volledig kaartvlak lichtoranje (`#FFF1DC`); **Gecontroleerd** krijgt een volledig lichtgroen kaartvlak (`#EEF7F0`). Deze achtergrond blijft zichtbaar bij selectie, hover en aanraking. Andere statussen behouden hun neutrale weergave; de feitelijke status, filters en verwerkingsregels blijven ongewijzigd.
- De niet-zichtbare status blijft via de toegankelijke naam van de openknop beschikbaar voor ondersteunende technologie.
- In de vaste mobiele actiebalk is **Meer** een ongekaderde actie, met dezelfde iconhoogte (44 px), totaalhoogte, tekstpositie en focusbehandeling als de andere acties. Geen extra knoprand of afwijkende knopachtergrond.

## PR #591 — bonnenlijsten zonder omvattend paneel (18 oktober 2026)

- In de mobiele bonnenlijsten van **Kassa** en **Uitpakken** staat **geen wit of ander omvattend paneel** achter de afzonderlijke bonkaarten. De lijstcontainer is transparant, zonder eigen rand of afronding; de lichtgroene schermachtergrond blijft tussen de kaarten zichtbaar.
- De checkbox voor selectie staat **naast en buiten de eigenlijke bonkaart**, rechtstreeks op de lichtgroene schermachtergrond.
- Alleen het klikbare individuele bonpaneel heeft een eigen afgeronde achtergrond en een subtiele schaduw. De kleur blijft oranje bij **Controle nodig**, lichtgroen bij **Gecontroleerd**, en wit bij overige statussen. Dit betreft uitsluitend de visuele presentatie; status, bonselectie en verwerking blijven ongewijzigd.

## PR #595 — onderhoudsmelding als headeroverlay

- De bestaande onderhoudsmelding staat op desktop en mobiel als vaste overlay over de header, zonder extra ruimte boven de header.
- Toon de tekst vetgedrukt op een dekkende lichtoranje achtergrond met donkere tekst en duidelijke rand. Lange berichten breken af en blijven binnen de viewport scrollbaar.
- Behoud de bestaande statusbron, verversingsinterval, aankondigingstekst en blokkeringsmelding. Bij normale status verdwijnt de overlay.

## Winkelkoppelingen — compact overzicht (PO, 23 oktober 2026)

De pagina **Winkelkoppelingen** toont zonder extra inleidend paneel één titel **Mijn winkelkoppelingen** en direct daaronder de bestaande `DataTable`, met uitsluitend de kolommen **Winkel**, **Laatst bijgewerkt** en **Status** (de actieknoppen staan in de Status-kolom). Geen samenvatting, technische uitleg of apart klantenkaartpaneel boven of onder deze overzichtstabel. De bij de gekozen winkel behorende bediening en uniforme voortgang volgen onder de tabel.

Voor Aldi en PLUS luidt de zichtbare statusknop **Geen koppeling mogelijk**, met eenvoudige uitleg dat er geen digitale kassabonnen via website of klantenpas beschikbaar zijn. De presentatie moet op desktop en mobiel begrijpelijk blijven; op mobiel worden de drie kolommen met compacte breedten en zonder technische extra kolommen getoond.

In alle gebruikerszichtbare teksten wordt waar mogelijk **Inhuis** gebruikt in plaats van de technische infrastructuurterm 'server'. Onderdelen die technisch `server` heten (variabelen, API's, interne statuscodes) blijven ongewijzigd om contractbreuk te vermijden. Voor onderhouduitleg is **Onderhoud aan Inhuis** de functionele benaming.


## Winkelkoppelingen: vaste paneelbreedte en Jumbo-koppelvenster — 23 oktober 2026

De drie-kolomstabel met **Winkel**, **Laatst bijgewerkt** en **Status** bepaalt de beschikbare paneelbreedte: alle onderliggende, op aanvraag zichtbare winkelpanelen gebruiken dezelfde breedte, zodat er bij het wisselen van winkel geen horizontale sprong optreedt. Kleinere mobiele viewports behouden binnen de tabel de bestaande horizontale scroll.

Voor Jumbo en Lidl toont **Laatst bijgewerkt** de geverifieerde laatste importdatum of, bij een eerste import, **1 januari van het voorafgaande jaar** als herkenbare startdatum. De `Vanaf`-datum in het onderliggende paneel komt overeen met diezelfde datum; gebruikers kunnen handmatig een andere periode kiezen. Na een succesvol afgesloten import kan de datum worden ververst.

De Jumbo-bedieningsrij plaatst **Open mijn Jumbo** links en **Eerste keer koppelen met Jumbo?** rechts. De tweede knop opent een modal met een naar de favorietenbalk sleepbare **Jumbo-bonnen ophalen**-knop. Deze modal sluit uitsluitend door **OK**, niet door Escape of klikken buiten de modal, en behoudt de toetsenbordfocus binnen het venster. Voor de openstaande modal blijven dezelfde bestaande Inhuis-knoppen en tekst-/contrastregels gelden.

## Winkelkoppelingen: niet-interactieve onbeschikbare status en uniforme retailerpanelen — 23 oktober 2026

Bij Aldi en PLUS is **Geen koppeling mogelijk** in de Status-kolom gewone tekst met de Inhuis-primaire donkergroene kleur; geen knop, hoveractie of toetsenbordfocus. De eenvoudige reden blijft beschikbaar via het label/de tooltip. De andere winkels houden een echte actieknop.

De onderste Jumbo- en Lidl-panelen hanteren dezelfde presentatievolgorde en maatvoering: dezelfde twee datumvelden, één horizontale actierij (**Open mijn [winkel]** links; **Eerste keer koppelen met [winkel]?** rechts) en voor de eerste keer dezelfde gedeelde overlay met sleepbare browserfavoriet. Beide overlays hebben één sluitactie, **OK**, en blijven staan bij Escape of klikken buiten het venster. Het technische verschil blijft intern: Lidl slaat een gewijzigde importperiode via de bestaande huishoudroute automatisch op zodra de gebruiker op **Open mijn Lidl** klikt. Alleen na bevestigde opslag wordt het Lidl-tabblad geopend. De extra knoppen **Periode opslaan** en **Automatische periode** en de bijbehorende waarschuwing zijn verwijderd; bij een fout krijgt de gebruiker één begrijpelijke melding en blijft de Lidl-bonophaalactie zonder effect. De bestaande bonimport en autorisatie blijven intact.

## Winkelkoppelingen: exacte gedeelde Jumbo/Lidl-paneelgeometrie (PO, 23 oktober 2026)

Beide winkelpanelen zijn één en dezelfde `RetailerReceiptPanel`-component. Kopieer de markup voor Jumbo en Lidl niet meer afzonderlijk. Gebruik dezelfde ene korte toelichting (‘Kies de periode en haal je kassabonnen op.’), dezelfde typografie, identieke datumveldvolgorde en verticale marges. De onderste acties staan in een vaste gedeelde tweekolomsindeling met op desktop 160 px voor **Open mijn [winkel]** en 240 px voor **Eerste keer koppelen met [winkel]?**. Op kleine schermen worden beide kolommen evenredig geschaald, waarbij hun posities en breedtes tussen winkels exact overeenkomen en knopteksten mogen afbreken. Na openen van Jumbo of Lidl mag geen verschil ontstaan in buitenbreedte, panelhoogte (zonder importresultaten), veldhoogte of verticale positie van de datums en knoppen. Provider-specifieke opslag, accountautorisatie, bonbevestiging, foutmeldingen en browseroverdracht blijven technische logica buiten dit gedeelde visuele component.

## Winkelkoppelingen: reguliere verticale afstanden in winkelpanelen (PO, 23 oktober 2026)

De onderste winkelpanelen behouden op mobiel dezelfde reguliere verticale tussenruimte als op desktop: 12 px tussen hoofdonderdelen en datumvelden, 6 px tussen datumlabel en invoerveld en 6 px boven toelichtingen. Bestaande interne afstanden van 10 of 6 px in overige winkelpanelen blijven behouden. Dit vervangt het eerdere besluit om mobiele detailregels op nul te zetten. De compacte overzichtstabel bovenaan blijft ongewijzigd. Jumbo en Lidl blijven dezelfde gedeelde component gebruiken; globale Input-opmaak wordt niet gewijzigd. Gerichte layoutcontroles gelden op 390, 500, 896 en 1280 px.

## Winkelkoppelingen: compacte mobiele hoofdtabel (PO, 23 oktober 2026)

Op mobiel wordt **Mijn winkelkoppelingen** weergegeven als één compacte rij per winkel in de bestaande `DataTable`, met éénmaal de kolomkoppen **Winkel**, **Laatst bijgewerkt**, **Status**. De algemene Instellingen-opmaak die tabelrijen omzet naar grote gestapelde kaartjes geldt niet voor uitsluitend deze tabel. Daardoor staan de winkelnaam, datum en actie naast elkaar in één korte rij, zonder telkens drie herhaalde labels en zonder extra binnenpanelen. De Status-knoppen blijven rechtstreeks bedienbaar en **Geen koppeling mogelijk** blijft niet-klikbare donkergroene tekst. Op desktop en alle andere mobiele Instellingen-tabellen verandert niets. Er gelden gerichte controles voor 390, 500 en 896 pixels; de zes winkelregels blijven in beeld en de tabel mag niet horizontaal uit het scherm lopen.


## Externe databases: automatisch producttype — 23 oktober 2026

Het bestaande detailpaneel toont **Automatisch producttype voor Bijna op** als
read-only resultaat, via dezelfde koppen, tekst en feedbacktypografie als de
omringende secties. De standaardflow vraagt geen varianttekst of bevestiging
van deze afgeleide indeling. Bij onvoldoende gegevens staat expliciet dat het
artikel voorlopig apart blijft en geen invoer nodig is. Bestaande optionele
platformtools voor bron-/GPC-beheer blijven beschikbaar. De verandering gebruikt
geen nieuwe kleuren, kader-, formulier- of navigatiepatronen. Zowel 390 als
1280 pixels worden gericht getest.

### GPC-selectie in Externe databases — 24 oktober 2026

Een keuzelijst die als keuze wordt gepresenteerd is bedienbaar zodra de
classificatiecontrole klaar is. De geselecteerde code wordt expliciet als
selectie getoond, met uitleg over generiek versus exact koppelen. Selecteren
is geen opslaan. Tijdens controleren of opslaan mag de bestaande centrale
select tijdelijk worden uitgeschakeld.

### Externe databases 2: zeven kandidaten per pagina — PO, 25 oktober 2026

Uitsluitend de onderste kandidatentabel toont maximaal **7 resultaten per pagina**
op desktop en mobiel. Meer kandidaten blijven beschikbaar via de bestaande
DataTable-paginering onder de tabel; filteren en sorteren bestrijken alle
opgehaalde resultaten en zetten de pagina terug op 1. De bovenste artikellijst
en de algemene standaard van 10 wijzigen niet. Het bestaande productpaneel
toont ook AH-/Jumbo-bronbewijs; naamsuggesties blijven expliciet herkenbaar.

### Externe databases 2: compacte kandidatentabel — PO, 25 oktober 2026

De eerste kolom toont alleen het volgnummer; de zichtbare kop **Voorkeur**
vervalt. **Herkenning** benoemt uitsluitend herkenning op naam zonder het woord
*Suggestie*, en in de kolom **Bron** wordt *Open Food Facts* afgekort tot **OFF**.
De toelichting boven de onderste tabel introduceert deze afkorting als
**Open Food Facts (OFF)**. De standaardmelding over Jumbo-producten die alleen
op naam overeenkomen wordt in dit paneel niet herhaald; eventuele aanvullende
bronwaarschuwingen blijven zichtbaar. Tussen paneeltitel en toelichting en
tussen toelichting en direct volgende tabel staat telkens één compacte
regel tussenruimte; geen lege melding mag een extra rij toevoegen.

### Artikel-synoniemen — PO, 26 oktober 2026

De actiebutton **Artikel-synoniemen** is beschikbaar voor Superusers en
Frontteamleden. Het scherm gebruikt AppShell, ScreenCard en de centrale DataTable
met selectie, kolomfilters, sortering, resize en standaardpaginering. De bulkknop
**Koppelen** staat bij de tabelacties onder de tabel en is inactief zonder selectie.
De zeven kolommen zijn: selectie (lege, smalle kolomkop); eerste artikelnaam, foto en winkel; tweede
artikelnaam, foto en andere winkel. De afbeelding gebruikt de gedeelde
Catalogusfoto met placeholder. Een zichtbare winkelaanduiding is altijd afkomstig
uit vastgelegde winkelinformatie. De knop Vernieuwen vervalt.
Catalogus desktop toont de numerieke, rechts uitgelijnde, sorteerbare en
filterbare kolom **Gekoppelde winkels** naast Huishoudartikelen. Het gaat om
unieke andere winkels van uitsluitend directe bevestigde synoniemkoppelingen;
de waarde staat ook op mobiel, in het artikeldetail en in de export.
Er is één korte toelichting over handmatig controleren en een link naar
Externe databases 2 voor ontbrekende codes. De mobiele header/Terug en feedback
komen uit de bestaande gedeelde componenten.

### Externe databases 2: vrij zoeken in OFF — PO, 26 oktober 2026

De vaste productgegevensregel is de enige toelichting in het automatische
kandidatenpaneel: eventuele bronstatusalinea's, bronbewijsdetails en links
worden daar niet meer getoond. Direct daarna staat de knop **Zelf zoeken in
OFF**. Deze opent een afzonderlijk scherm met één vrij zoektekstveld en
een zoekknop. OFF-resultaten komen in een gewone DataTable, zonder eigen
kolomfilters en met zeven kandidaten per pagina en paginering als er meer
resultaten zijn. Het zoekscherm heeft **geen extra Terugknop**: de mobiele gedeelde
header-Terug blijft bestaan. De Overeenkomstkolom toont een niet-nul
productrelevantiescore (winkelnamen worden niet als naamovereenkomst geteld)
en bepaalt standaard de rangorde; niet-berekenbare scores verschijnen als
streepje, niet als verzonnen 0%. Dubbelklik op desktop, tik op mobiel of
Enter op een rij opent de waarschuwingsoverlay met uitsluitend de vraag
**Weet u zeker dat u dit artikel wilt koppelen?** en **Annuleren** / **OK**,
zonder extra titel of toelichting. Bij OK valideert de backend een kortlevend,
cryptografisch ondertekend OFF-zoekbewijs, bronbonartikel en GTIN, zonder
tweede externe OFF-opvraag. De centrale Catalogus koppelt alleen bij de
verplichte identiteit-, merk- en officiële GS1 GPC-controles. Een verlopen
bewijs of ontbrekende officiële classificatie geeft na OK een foutmelding
in **Externe databases 2**; nooit een onterechte succesmelding of databasewrite.
Ook na een bevestigingsfout of timeout keert **OK** terug naar het overzicht.
Een niet ontvangen serverbevestiging wordt altijd als **niet bevestigd**
getoond. Een succesmelding verdwijnt na maximaal vier seconden. Een mislukte
Catalogusmutatie is een blijvende, aanklikbare foutregel tot de gebruiker die
zelf sluit of het scherm verlaat, zodat de afwijzing niet onopgemerkt verdwijnt.
Alleen bij bevestigd `linked: true` verschijnt de succesmelding. **Annuleren** sluit
alleen de dialoog en blijft op het zoekscherm zonder koppeling.
OFF-zoeken zelf blijft uitsluitend lezen.

### Externe databases 2: tellerkleuren en gezamenlijk OFF-zoekveld — PO, 28 oktober 2026

De drie klikbare statusfilters boven de ED2-tabel hebben elk een herkenbare
achtergrond: **Gekoppeld** lichtgroen (`#D9F5E0`), **Niet gekoppeld**
lichtoranje (`#FFD9A8`) en **Classificatie ontbreekt** wit (`#FFFFFF`).
Alle drie gebruiken donkergroene tekst en rand; de actieve selectie behoudt
een duidelijk zichtbaar extra kader. De statustekst blijft altijd zichtbaar,
zodat kleur niet als enig betekenissignaal dient.

Het afzonderlijke scherm **Zelf zoeken in OFF** heeft één invoerveld voor
omschrijving, merk, trefwoorden of barcode. Een invoer met alleen cijfers
wordt als GTIN/EAN behandeld (8, 12, 13 of 14 cijfers); anders zoekt Inhuis
op tekst. Het onderscheid verandert geen backendvalidatie of expliciete
koppelbevestiging. De centrale knop **Zoeken** staat direct rechts naast het
veld, met exact gelijke invoer-/knophoogte en gelijk uitgelijnde onderranden,
ook bij een smalle mobiele viewport. Er komen geen extra zoekvelden of
afwijkende knopcomponenten bij.

### Externe databases 2: artikelkop en bulkverwerking — PO, 28 oktober 2026

In **Zelf zoeken in OFF** staat direct boven het gecombineerde zoekveld de
geselecteerde bonartikelnaam **vetgedrukt**; het voorafgaande label `Artikel:`
blijft normaal. De ED2-hoofdtabel heeft een smalle selectiekolom zonder titel.
**Alles op pagina** selecteert uitsluitend de getoonde tabelpagina; een selectie
op andere pagina's blijft bewaard. **Exporteren** en **Ontkoppelen** staan als
bulkacties onder de tabel en zijn zichtbaar maar inactief zonder passende
selectie. Exporteren levert uitsluitend de geselecteerde artikelen als CSV;
ontkoppelen vraagt eerst expliciete bevestiging met **Annuleren** en **OK**.
Alleen een aantoonbare OFF-koppeling kan ontkoppeld worden, maximaal honderd
bonartikelen per keer. Bij een serverfout of verouderde selectie blijft de
actie zonder succesvolle melding. Na een geslaagde ontkoppeling worden de
tellers en de tabel ververst. Bestaande DataTable-opmaak, sortering, filters,
resize, paginering en mobiele bediening blijven leidend.

### Externe databases 2: GS1-classificatie aanvullen en tekstfilters — PO, 28 oktober 2026

De kolomtitel **Status** wordt **GS1-class.**; de kolom blijft de bekende
Nederlandse statusteksten weergeven. Onder zowel **Art.code** als
**GS1-class.** staat het standaard tekstfilter van de gedeelde `DataTable`,
zonder afwijkende keuzelijst. De drie gekleurde tellers blijven aparte
klikfilters en kunnen samen met de tekstfilters worden gebruikt.

Bij **Classificatie ontbreekt** opent een compact GS1-aanvulpaneel in ED2,
met de bonartikelnaam vetgedrukt, officiële GS1-voorstellen en één zoekveld
voor code of Nederlandse omschrijving. De kandidaatregels volgen de gewone
`DataTable` met maximaal zeven per pagina. Een regel kiezen is géén mutatie;
**Classificatie opslaan** vraagt expliciet **Annuleren/OK**. Bij bewezen
succes sluit het paneel en vernieuwt de bovenste tabel inclusief tellers;
bij fouten blijft de gebruiker op het paneel met een leesbare melding.


### Catalogus: artikelclassificaties en leesbare OFF-voorstellen — PO, 28 oktober 2026

Het scherm **Artikelclassificaties toekennen** gebruikt de bestaande, gedeelde
`DataTable` met een selectiekolom zonder titel, standaard kolomfilters,
sortering, verstelbare kolombreedtes en paginering van acht rijen. Er zijn
geen afzonderlijke zoekvelden en geen extra navigatie per honderd rijen.
De titel en de tekst daaronder zijn respectievelijk **Artikelclassificaties
toekennen** en **Via OFF kun je suggesties opvragen voor de artikelclassificatie.**

De tabel toont **Artikel**, **Barcode**, **Artikelclassificatie** en
**Voorgestelde artikelclassificatie**. De volledige tabelbreedte, het
tabelkader, de paginering en de vier bulkacties zijn op elkaar uitgelijnd,
zonder een lege randstrook aan de rechterzijde. Onder de paginering staan
**Voorstel ophalen**, **Voorstel bevestigen**, **Exporteren** en
**Classificatie verwijderen**; ze blijven zichtbaar en worden alleen actief
bij een passende selectie. Bevestiging slaat uitsluitend een expliciet
beoordeelde classificatie op; verwijderen vraagt een aparte bevestiging en
laat het artikel, de barcode en de wijzigingshistorie ongemoeid.

Lange voorgestelde classificaties mogen compact worden afgekapt in een
tabelcel, maar de voorsteltekst is altijd aanklikbaar. Die klik opent een
duidelijke, gecentreerde Inhuis-melding met **volledig witte ondoorzichtige
achtergrond**, een herkenbare donkergroene rand en goed afbrekende regels.
De volledige categorie, artikelnaam, barcode en eventuele waarschuwing
moeten leesbaar zijn zonder onderliggende tabeltekst die doorschijnt.
De gebruiker sluit de melding via **Sluiten** of een klik buiten de melding.
Een herhaalde klik op hetzelfde voorstel opent dezelfde melding opnieuw.

Wanneer meerdere geselecteerde artikelen via **Voorstel ophalen** worden
beoordeeld, verschijnt uitsluitend het **eerste geslaagde OFF-voorstel
direct bij ontvangst** automatisch in de melding. De overige OFF-verzoeken
lopen vervolgens op de achtergrond door en vullen hun eigen tabelrij,
zonder de bestaande melding te vervangen of een tweede automatische
overlay te tonen. Na sluiten kan de gebruiker elk afzonderlijk voorstel
zelf opnieuw openen. Het tonen of sluiten van voorstellen is geen
classificatiebevestiging.

### Catalogus: zichtbare artikelclassificatie en standaardfilter — PO, 28 oktober 2026

De aparte, handmatig bevestigde **Artikelclassificatie** staat in de
hoofdtabel **Catalogus** direct naast **Universeel artikel**, zodat deze niet
buiten beeld aan het verre rechtereinde van de tabel verdwijnt. Dezelfde
bevestigde categorie wordt in het mobiele overzicht en het artikeldetail
getoond, zonder bestaande GS1/GPC-velden te veranderen.

In **Artikelclassificaties toekennen** start het standaard tekstfilter onder
**Artikelclassificatie** met **Niet geclassificeerd**. De waarde in het filter
moet gelijk zijn aan de zichtbare tekst in de cel en aan de filterbare waarde:
een lege, oningevulde classificatie is dus niet intern een lege string voor de
gebruiker. Na bevestigen verdwijnt het artikel uit de standaardselectie met
ontbrekende classificaties, maar is via wissen van het filter of in de
Catalogus weer terug te vinden. Sortering en zoeken behandelen de status
op beide schermen identiek.


## Synoniemenanalyse in centrale Catalogus — 29 oktober 2026

De Catalogus toont voor Superusers en Frontteamleden zowel op desktop als mobiel
een actie **Synoniemenanalyse**. De route gebruikt de bestaande gedeelde mobiele
sticky header en de bestaande platformrol-/permissieafscherming.

Het scherm gebruikt de bestaande **ScreenCard**, **Button**, **Select** en
**DataTable** in plaats van nieuwe tabel-, filter- of navigatiecomponenten.
De indeling bestaat uit:
- een compacte rij tellers voor rechtstreeks bevestigde artikelparen, open
  tekstkandidaten, artikelen zonder gevonden kandidaat en artikelen waarvan
  de winkel onbekend is;
- filters op artikelsoort, winkel, status en zoektekst;
- een standaard gepagineerde tabel met artikelsoort, winkel en aantallen;
- een tweede standaard gepagineerde tabel voor de betrokken Catalogusartikelen,
  met Catalogusfoto, rechtstreeks gekoppelde winkels, voorstelstatus en een
  doorklikactie naar de bestaande handmatige Artikel-synoniemen-beoordeling.

Getallen zijn uitsluitend gebaseerd op actuele centrale Catalogusgegevens.
De UI vermeldt dat een tekstkandidaat géén bewezen functionele gelijkwaardigheid
is, dat ontbrekende kandidaten geen ontbrekend supermarktassortiment bewijzen
en dat alleen rechtstreeks bevestigde relaties als gekoppeld tellen.
Een product mag tegelijk gekoppelde winkels en nog te beoordelen voorstellen
hebben. Ontbrekende winkelidentiteit heet **Winkel onbekend** en wordt niet
als werkelijk aanwezige winkel gepresenteerd.

De tellers gebruiken een neutrale, compacte opmaak met dezelfde bestaande
design tokens; de eigen scherm-CSS beperkt zich tot grid/spacing en de
responsieve stapeling op maximaal 720px. Tabelkolommen, uitlijning,
paginering en actieknoppen volgen de cumulatieve Inhuis-styleguide.


### Synoniemenanalyse: directe artikelwerklijst — PO, 29 oktober 2026

De startweergave toont **één standaard DataTable met individuele artikelen**,
geen technische GPC-matrix boven de werklijst. Boven die tabel staan vier
compacte aanklikbare tellers voor artikelen met **0, 1, 2 of 3+** rechtstreeks
bevestigde synoniemen. De actieve teller gebruikt dezelfde primaire Inhuis-token
en een subtiele groene achtergrond. Nogmaals klikken schakelt het filter uit.
De bestaande gedeelde DataTable levert zoeken, sorteren en pagineren.

Een klik op een artikel toont **onder de tabel** een tweede standaard DataTable
met maximaal vijf kandidaatartikelen, hun foto, winkel en kenmerken. De
lege selectiekolom gebruikt een radioknop voor precies één kandidaat.
Dubbelklik op een kandidaat bevestigt direct; een enkele selectie gevolgd door
**Merk kandidaat aan als synoniem** doet hetzelfde. Totdat die bevestiging
gebeurt, verandert de Catalogus niet. Succes ververst de tellers, het artikel
en de beide directe gekoppelde Catalogusartikelen; errors blijven zichtbaar.
De actie is uitsluitend beschikbaar voor Superuser en Frontteam, ook op mobiel.


### Synoniemenanalyse: compacte tabel en dubbelklik — PO, 29 oktober 2026

De artikelnaam in de hoofdtabel is **gewone tekst**, nooit een knop of een
gekleurde actietegel. De volledige tabelrij opent het kandidaatpaneel
**uitsluitend na dubbelklik**, niet na één klik; toetsenbordbediening blijft
mogelijk met Enter op een gefocuste rij. Dit gebruikt de bestaande gedeelde
DataTable en verandert geen overige tabellen. Op de hoofdpagina ontbreken de
redundante zwarte toelichtingsalinea's en de dubbele paginatitel; tellers,
filters en hoofdtabel staan direct onder elkaar. Foutmeldingen en laadstatus
blijven beschikbaar. Het paneel onder de tabel krijgt uitsluitend een korte
titel met artikelnaam, de kandidaat-DataTable en de benodigde selectie-/koppel-
acties; verklarende zwarte alinea's vervallen. De bevestigingsknop blijft
**onder** de kandidaat-tabel aanwezig.


### Synoniemenanalyse: filters en tabelscroll — PO, 29 oktober 2026

Verwijder alle extra filtervelden boven de Synoniemenanalyse-tabel; het
centrale DataTable-filter onder de kolomkoppen heeft exact dezelfde functie.
De vier synoniem-tellers blijven beschikbaar. De standaard paginering en
kolom-resize blijven behouden. De schermspecifieke tabel-wrapper toont zijn
volledige pagina van tien artikelen, zodat de horizontale scrollbar **onder**
de laatste tabelrij wordt geplaatst en nooit door de tekst loopt. Dezelfde
regel geldt voor de onderste kandidaattabel met maximaal vijf rijen.
Verwijder de aparte knop **Sluiten** bij de kandidaatsectie, maar behoud de
bevoegde koppelactie onder de kandidaattabel en foutmeldingen bij problemen.


## Catalogusdetail — universele naam wijzigen (30 oktober 2026)

- Op zowel desktop als mobiel staat naast de **universele artikelnaam** in het Catalogusdetail de actie **Naam wijzigen** voor gebruikers met de bestaande platformpermissie `platform.catalog.update`. Een gewone huishoudbeheerder kan wel een ontbrekende GTIN bijdragen, maar mag zonder catalogusbevoegdheid geen bestaande universele naam overschrijven.
- De actie toont een compact invoerveld op dezelfde plek met **Opslaan** en **Annuleren**; het standaard Catalogusdetail blijft leesbaar. Invoer en knoppen volgen de bestaande Inhuis-kleurtokens, typografie en responsieve regel.
- Een wijziging verandert alleen de gedeelde artikelnaam en de daarbij horende productvingerafdruk. De artikel-ID, barcode, voorraad, huishoudkoppelingen en kassabonregels blijven bestaan.
- Bij een ondertussen gewijzigde naam of conflict met een ander artikel meldt Inhuis de fout en wordt niet stilzwijgend samengevoegd.
