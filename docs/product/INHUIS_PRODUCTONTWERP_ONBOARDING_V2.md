# Inhuis — Productontwerp Onboarding v2

**Status:** canoniek productontwerp voor de onboarding-/instellingenlijn  
**Product:** Inhuis (repository: Rezzerv)  
**Versie:** 2.0  
**Datum:** 2026-08-23  
**Repository-baseline bij opstellen:** `4575ea2325ed8d4adb27187a24ff2e7d90ef4953`  
**Eigenaar productbeslissingen:** Product Owner

> Dit document is de productmatige source of truth voor de nieuwe onboarding en de daarvan afgeleide gebruikersinrichting van Inhuis. Wijzigingen in dit ontwerp horen expliciet te worden besloten en via versiebeheer te worden vastgelegd. Technische implementatie mag dit ontwerp niet stilzwijgend verbreden of versmallen.

---

## 1. Productuitgangspunt

Inhuis wordt **geen brede app die iedere gebruiker standaard alle functies aanbiedt**.

De app moet eerst begrijpen **wat de gebruiker met Inhuis wil bereiken** en daarna alleen de relevante inrichting, schermen, vragen en instellingen aanbieden.

De kernregel is:

> **Inhuis past zich aan de gebruiker aan. De gebruiker hoeft zich niet aan Inhuis aan te passen.**

Daaruit volgen vier ontwerpprincipes:

1. **Doel-first onboarding** — eerst bepalen wat de gebruiker wil, daarna pas configureren.
2. **Smal starten** — alleen vragen en functies tonen die voor dat gebruiksdoel nodig zijn.
3. **Later uitbreiden** — een eerste keuze is geen permanente beperking.
4. **Rol en productvoorkeur scheiden** — autorisatie bepaalt wat iemand mág; gebruiksdoel bepaalt wat iemand nódig heeft en dus te zien krijgt.

---

## 2. De drie startprofielen

De eerste inhoudelijke keuze van een nieuwe huishoudgebruiker is één van drie startprofielen.

| Startprofiel | Kernvraag | Betekenis |
|---|---|---|
| **Inhuis halen** | *Wat heb ik nodig?* | Ondersteuning bij aanvullen, boodschappen en aankopen. |
| **Wat Inhuis** | *Wat heb ik?* | Overzicht houden van bezittingen/voorraad zonder dat exacte locaties noodzakelijk zijn. |
| **Waar Inhuis** | *Waar ligt het?* | Bezittingen/voorraad beheren met locaties en eventueel exacte sublocaties. |

Deze drie profielen zijn **geen rollen** en ook geen drie afzonderlijke applicaties. Zij bepalen de **startinrichting** en de relevante vervolgstappen.

Een gebruiker kiest tijdens de eerste onboarding **één startprofiel**. Later kunnen andere mogelijkheden worden toegevoegd.

---

## 3. Circulair productmodel

De drie profielen vormen samen een natuurlijke kringloop:

**nodig hebben → Inhuis halen → weten wat je hebt → Wat Inhuis → weten waar het ligt → Waar Inhuis → gebruiken/verbruiken → opnieuw nodig hebben**

Een gebruiker hoeft niet de hele kringloop te gebruiken.

Voorbeelden:

- Iemand kan jarenlang alleen **Inhuis halen** gebruiken.
- Een gebruiker kan starten met **Wat Inhuis** en later exacte locaties toevoegen via **Waar Inhuis**.
- Een gebruiker van **Waar Inhuis** kan ook boodschappenondersteuning activeren zonder opnieuw onboarding te doorlopen.

De oorspronkelijke startkeuze blijft beschikbaar als productcontext, maar actieve mogelijkheden mogen in de tijd groeien.

---

## 4. Eerste onboardingvraag

De eerste inhoudelijke onboardingvraag luidt:

# Waar wil je Inhuis mee beginnen?

### Inhuis halen
**Ik wil weten wat ik nodig heb.**  
Help mij bepalen wat aangevuld moet worden en boodschappen doen.

### Wat Inhuis
**Ik wil overzicht van wat ik heb.**  
Geef mij een eenvoudig overzicht van mijn spullen of voorraad.

### Waar Inhuis
**Ik wil weten waar alles ligt.**  
Help mij spullen en voorraad op de juiste plek terug te vinden.

Onder de keuzes staat altijd een geruststellende boodschap in deze betekenis:

> **Je kunt later altijd andere mogelijkheden toevoegen.**

De eerste keuze wordt dus niet als een technisch of commercieel slot gepresenteerd.

---

## 5. Gemeenschappelijke minimale huishoudbasis

Alle gewone nieuwe huishoudgebruikers hebben slechts een kleine gemeenschappelijke basis nodig.

| Gegeven | Verplicht in onboarding? | Reden |
|---|---:|---|
| Startprofiel | Ja | Bepaalt de relevante vervolgstappen. |
| Naam huishouden | Ja | Nodig voor de gedeelde huishoudcontext. |
| Alleen of samen gebruiken | Ja | Bepaalt of leden/invitatie relevant zijn. |
| Ander lid uitnodigen | Nee | Mag later; onboarding mag hier niet op blokkeren. |

Niet standaard vragen tijdens de eerste onboarding:

- exacte locaties;
- sublocaties;
- boodschappenfrequentie;
- technische instellingen;
- geavanceerde automatiseringsregels;
- alle mogelijke meldingsvarianten;
- alle functies die niet bij het gekozen doel horen.

Een instelling wordt bij voorkeur pas gevraagd wanneer de gebruiker begrijpt **waarom** die nodig is.

---

## 6. Profiel: Inhuis halen

### 6.1 Doel

De gebruiker wil vooral:

> **weten wat nodig is en dat gemakkelijk in huis halen.**

Exacte opslaglocaties zijn hiervoor niet nodig.

### 6.2 Relevante kernfuncties

Primair:

- Bijna op;
- Winkelen;
- aankopen/kassabon verwerken;
- optioneel Gerechten/inspiratie.

Minder of niet prominent bij de start:

- locatiebeheer;
- sublocaties;
- exact uitpakken naar opslagplek;
- uitgebreide voorraadadministratie.

### 6.3 Minimale onboardingvragen

Alleen vragen die direct waarde leveren, bijvoorbeeld:

1. Wil je een eenvoudige voorraad gebruiken om te bepalen wat bijna op is?
2. Wil je bijna-op meldingen ontvangen?
3. Wil je aankopen via kassabonnen verwerken? **Nu / later**.
4. Wil je Gerechten gebruiken als inspiratie voor boodschappen? **Nu / later**.

Niet alle vragen hoeven per se in de eerste wizard; sommige kunnen contextueel bij eerste gebruik worden gesteld.

### 6.4 Afgeleide instellingen

Relevante instellingen:

- bijna-op signalering;
- minimum-/standaardaantallen indien van toepassing;
- meldingen;
- kassabonverwerking indien geactiveerd;
- Gerechten indien geactiveerd.

Niet standaard tonen:

- locaties beheren;
- sublocaties;
- exacte uitpakregels.

### 6.5 Locatieniveau

**Geen gebruikerszichtbare locatie mag verplicht zijn puur omdat het oude datamodel een locatie verwacht.**

Voor dit profiel is het gewenste productniveau:

`location_tracking_level = none`

De technische realisatie daarvan wordt in een afzonderlijke implementatieslice vastgesteld.

---

## 7. Profiel: Wat Inhuis

### 7.1 Doel

De gebruiker wil vooral:

> **weten wat hij heeft, zonder verplicht exact vast te leggen waar alles ligt.**

Dit kan breder zijn dan boodschappen en op termijn ook andere bezittingen omvatten.

### 7.2 Relevante kernfuncties

Primair:

- bezittingen-/voorraadoverzicht;
- aanwezigheid of aantallen;
- optioneel globale locaties;
- optioneel bijna-op;
- optioneel Winkelen.

Niet standaard nodig:

- exacte sublocaties;
- gedetailleerd uitpakken;
- locatiehiërarchie tot kast/plank/bak.

### 7.3 Minimale onboardingvragen

1. Wil je alleen weten **óf** je iets hebt, of ook **hoeveel**?
   - aanwezigheid;
   - aantallen.
2. Wil je globale plekken gebruiken?
   - nee;
   - ja, bijvoorbeeld Keuken, Garage, Badkamer.
3. Wil je bijna-op signalering gebruiken?
4. Wil je vanuit je overzicht ook boodschappen kunnen maken?

### 7.4 Afgeleide instellingen

Afhankelijk van de keuzes:

- aanwezigheid versus aantallen;
- globale locaties;
- bijna-op;
- Winkelen.

Exacte sublocaties blijven uit beeld totdat de gebruiker **Waar Inhuis** activeert.

### 7.5 Locatieniveau

Productmatig zijn twee varianten toegestaan:

- `none` — geen locatie nodig;
- `global` — alleen een globale hoofdlocatie.

---

## 8. Profiel: Waar Inhuis

### 8.1 Doel

De gebruiker wil vooral:

> **precies kunnen terugvinden waar spullen of voorraad liggen.**

### 8.2 Relevante kernfuncties

Primair:

- hoofdlocaties;
- sublocaties;
- voorraad/bezittingen koppelen aan plek;
- uitpakken;
- optioneel kassabonverwerking;
- optioneel bijna-op en Winkelen.

### 8.3 Minimale onboardingvragen

1. Welke hoofdlocaties wil je gebruiken?
   - bijvoorbeeld Keuken, Bijkeuken, Garage, Schuur, Zolder, Badkamer.
2. Wil je locaties nu al verfijnen met sublocaties?
   - bijvoorbeeld Voorraadkast, Koelkast, Kast links, Stelling, Lade 2.
3. Wil je direct starten met Uitpakken?
4. Wil je kassabonnen gebruiken om nieuwe aankopen sneller toe te voegen?
5. Wil je ook bijna-op signalering gebruiken?

Ook hier geldt: verfijning mag later. De onboarding mag geen inventarisatieproject worden.

### 8.4 Locatieniveau

Productmatig:

`location_tracking_level = exact`

Exact betekent dat de gebruiker locatiebeheer als actief onderdeel van zijn productervaring heeft gekozen. Dat sluit niet uit dat individuele artikelen tijdelijk minder specifiek zijn vastgelegd.

---

## 9. Progressieve en contextuele onboarding

Onboarding is niet één lange eenmalige wizard.

Na de initiële start kan Inhuis op relevante momenten kleine aanvullende vragen stellen.

Voorbeelden:

- Bij eerste kassabon: **Wil je dat aankopen automatisch aan je overzicht worden toegevoegd?**
- Bij eerste gebruik van Uitpakken: **Wil je na iedere aankoop direct een opslaglocatie kiezen?**
- Bij groei van Wat Inhuis: **Wil je voortaan ook vastleggen waar deze spullen liggen?**

Ontwerpregel:

> **Vraag een instelling pas wanneer de gebruiker begrijpt waarom die instelling nodig is.**

---

## 10. Circulair uitbreiden via Instellingen

In Instellingen komt op termijn een centrale ingang met een naam in deze betekenis:

# Wat wil je met Inhuis doen?

Voorbeeld:

| Mogelijkheid | Status |
|---|---|
| Inhuis halen | Actief / Toevoegen |
| Wat Inhuis | Actief / Toevoegen |
| Waar Inhuis | Actief / Toevoegen |

Wanneer een gebruiker een extra mogelijkheid activeert, vraagt Inhuis **alleen de aanvullende informatie die nog ontbreekt**.

Voorbeeld:

- Start: **Inhuis halen**.
- Later: **Wat Inhuis** toevoegen → vraag aanwezigheid/aantallen en eventueel globale locaties.
- Nog later: **Waar Inhuis** toevoegen → vraag locatie-inrichting en gewenste verfijning.

Reeds bekende gegevens zoals huishoudnaam, account en eerdere voorkeuren worden niet opnieuw gevraagd.

---

## 11. Dynamische navigatie

Inhuis heeft één applicatie, maar de navigatie hoeft niet voor iedereen dezelfde nadruk te hebben.

### Startaccent Inhuis halen

Prominent:

- Bijna op;
- Winkelen;
- kassabon/aankopen;
- eventueel Gerechten.

Minder prominent of onder Meer:

- uitgebreid Overzicht;
- Locaties;
- Uitpakken.

### Startaccent Wat Inhuis

Prominent:

- Overzicht;
- eventueel Bijna op;
- eventueel Winkelen;
- Meer.

Minder prominent totdat geactiveerd:

- exacte Locaties;
- Uitpakken.

### Startaccent Waar Inhuis

Prominent:

- Overzicht;
- Locaties;
- Uitpakken;
- eventueel Winkelen/Bijna op.

Dynamische navigatie is een vervolgslice en wordt **niet** onderdeel van de eerste onboarding-foundation-PR.

---

## 12. Dynamische Instellingen

Instellingen worden niet alleen door autorisatie bepaald, maar ook door productrelevantie.

### Altijd relevante categorieën

Voor gewone huishoudgebruikers, voor zover hun rol dit toestaat:

- Mijn account;
- Huishouden;
- leden/samen gebruiken;
- Wat wil je met Inhuis doen?;
- meldingen;
- privacy, hulp en over.

### Voorbeeld: Inhuis halen

Wel relevant:

- bijna-op;
- boodschappen-/winkelvoorkeuren;
- kassabonverwerking indien actief;
- Gerechten indien actief.

Niet standaard relevant:

- sublocatie-instellingen;
- exacte uitpakregels.

### Voorbeeld: Waar Inhuis

Wel relevant:

- locaties;
- sublocaties;
- uitpakken;
- locatiegedrag;
- eventueel kassabon-toewijzing.

Een instelling die productmatig niet relevant is, hoeft niet als een uitgeschakelde technische optie aan de gebruiker te worden getoond.

---

## 13. Rollen, permissions en gebruiksprofielen blijven gescheiden

De afgeronde 9.1-autorisatiearchitectuur blijft leidend.

### Autorisatie beantwoordt

> **Mag deze actor deze actie uitvoeren?**

### Productconfiguratie beantwoordt

> **Is deze mogelijkheid voor dit huishouden actief/relevant en moet zij aan deze gebruiker worden gepresenteerd?**

Voorbeeld:

- Rol: **Beheerder**.
- Context: `regular`.
- Startprofiel: `inhuis_halen`.
- Actieve mogelijkheden: shopping, almost-out, receipt processing.
- Locatieniveau: `none`.

Een startprofiel wordt dus **nooit** een autorisatierol zoals `household.admin`.

Nieuwe productlogica mag geen terugkeer veroorzaken naar hardcoded rolchecks als vervanging van bestaande canonieke permissions.

---

## 14. Huishoudniveau versus accountniveau

De functionele inrichting hoort primair bij het **huishouden**, omdat leden dezelfde gedeelde werkelijkheid gebruiken.

Huishoudgebonden voorbeelden:

- actieve Inhuis-mogelijkheden;
- voorraadregistratieniveau;
- locatieniveau;
- huishoudbrede automatisering;
- globale locatie-inrichting.

Persoonsgebonden voorbeelden:

- persoonlijke notificaties;
- eventuele persoonlijke presentatievoorkeuren;
- persoonlijke privacy-/toestemmingskeuzes waar van toepassing.

Het moet worden voorkomen dat twee leden van hetzelfde huishouden verschillende waarheden hebben over bijvoorbeeld het bestaan van exacte locaties.

---

## 15. Conceptueel configuratiemodel

Onderstaande velden zijn een productmodel, geen definitieve databasespecificatie.

| Concept | Voorbeeldwaarden | Betekenis |
|---|---|---|
| `primary_use_case` | `inhuis_halen`, `wat_inhuis`, `waar_inhuis` | Waarmee het huishouden begon. |
| `onboarding_status` | `not_started`, `in_progress`, `completed` | Status van de initiële inrichting. |
| `onboarding_version` | `2` | Maakt toekomstige onboardingmigraties mogelijk. |
| `inventory_tracking_level` | `none`, `presence`, `quantity` | Hoe gedetailleerd bezit/voorraad wordt gevolgd. |
| `location_tracking_level` | `none`, `global`, `exact` | Hoe gedetailleerd locaties worden gevolgd. |
| `enabled_capabilities` | set/lijst | Welke productmogelijkheden actief zijn. |
| `onboarding_completed_at` | timestamp | Audit-/productcontext. |
| `onboarding_step` | optioneel | Hervatten na onderbreking. |

Niet alle concepten hoeven in de eerste implementatieslice te worden opgeslagen. De technische specificatie bepaalt per slice het minimale noodzakelijke contract.

---

## 16. Huidige repositorytoestand — relevante inventarisatie

De inventarisatie op baseline `4575ea2325ed8d4adb27187a24ff2e7d90ef4953` laat het volgende zien.

### 16.1 Nog geen echte onboarding-state machine

Na login navigeert de frontend rechtstreeks naar `/home`.

Relevante code:

- `frontend/src/features/auth/LoginPage.jsx`
- `frontend/src/app/router/AppRouter.jsx`

Er bestaat momenteel geen canonieke onboardingroute of opgeslagen onboardingstatus.

### 16.2 De huidige startpagina is breed

`frontend/src/features/home/HomePage.jsx` bevat standaard een brede set functies. Zichtbaarheid is nu vooral rol-/autorisatiegedreven, niet gebruiksdoelgedreven.

Dit ontwerp introduceert daar later een tweede dimensie naast autorisatie: **productrelevantie/capabilities**.

### 16.3 Instellingen zijn eveneens breed

`frontend/src/features/settings/SettingsPage.jsx` toont een algemene verzameling instellingen, voor zover permissions toegang toestaan.

Er bestaat nog geen capability-afhankelijke instellingenstructuur.

### 16.4 Huishoudbeheer bestaat al

`frontend/src/features/settings/SettingsHouseholdPage.jsx` en de bijbehorende backendroutes ondersteunen reeds:

- huishoudnaam;
- leden;
- rollen;
- koppelen/ontkoppelen.

Deze canonieke huishoudlogica kan voor onboarding worden hergebruikt.

### 16.5 Huidig leden koppelen is nog geen echte uitnodigingsflow

Een nieuw huishoudaccount wordt nu door de beheerder aangemaakt/gekoppeld en vereist bij een nieuw account een wachtwoord.

Dit is productmatig iets anders dan:

**uitnodigingsmail → ontvanger accepteert → ontvanger maakt/logt zelf in → membership ontstaat.**

Een echte uitnodigingsflow blijft daarom een aparte vervolgstap.

### 16.6 Reguliere zelfregistratie ontbreekt nog

De productieflow bevat login/session/logout, maar er is nog geen volwaardige consumentenflow:

**registreren → eigen huishouden creëren → Beheerder → onboarding.**

Dit is een voorwaarde voor een volledige nieuwe-gebruiker-instroom en krijgt een aparte foundation-slice.

### 16.7 Locaties en sublocaties bestaan al

`frontend/src/features/settings/SettingsLocationsPage.jsx` en backendlocatieroutes vormen een goede basis voor **Waar Inhuis**.

De fout in het huidige productmodel is niet dat locatiebeheer ontbreekt, maar dat het nog niet afhankelijk is gemaakt van het gekozen gebruiksdoel.

### 16.8 Nieuwe voorraadregel verwacht nu een hoofdlocatie

In `backend/app/schemas/inventory.py` is bij `InventoryCreate` momenteel `space_id` verplicht en `sublocation_id` optioneel.

Dat botst productmatig met:

- **Inhuis halen** zonder gebruikerszichtbare locatie;
- **Wat Inhuis** met geen of alleen globale locatie.

De oplossing hiervan hoort in een aparte voorraad-/locatiesemantiek-slice en wordt niet stilzwijgend in de onboarding-foundation meegenomen.

---

## 17. Migratie van bestaande gebruikers

Bij introductie van onboarding v2 mogen bestaande huishoudens **niet ineens verplicht opnieuw door onboarding**.

Productregel:

> **Nieuwe onboarding geldt vooruit voor nieuwe huishoudens en niet automatisch met terugwerkende kracht.**

Daarom moeten bestaande huishoudens bij introductie veilig als reeds ingericht worden behandeld, tenzij later expliciet anders besloten.

Bestaande gebruikers kunnen later vrijwillig via **Wat wil je met Inhuis doen?** nieuwe capabilities activeren.

---

## 18. Nieuwe gebruiker en accountinstroom

Voor een volledige consumentenflow is productmatig een instroom nodig in deze richting:

**Account maken → eigen huishouden creëren → automatisch bevoegde huishoudbeheercontext → onboarding → normale app**

De exacte account-/verificatie-/wachtwoordflow is nog geen definitief onderdeel van dit document en wordt in een aparte technische/product-slice uitgewerkt.

Belangrijke randvoorwaarde:

- platformcontexten zoals `system` en `none` doorlopen geen gewone huishoudonboarding;
- een uitgenodigd Lid richt niet zelfstandig het gedeelde huishouden opnieuw in;
- structurele huishoudconfiguratie wordt alleen gewijzigd door een actor met de daarvoor canonieke permission.

---

## 19. Uitnodigingen

De productrichting is een echte uitnodigingsflow:

**beheerder voert e-mailadres in → uitnodiging wordt verstuurd → ontvanger accepteert → ontvanger logt in of maakt account → wordt Lid van het huishouden**.

Deze flow is waardevol maar wordt **niet** in de eerste onboarding-foundation-PR opgenomen, om scopevermenging met e-mailtokens, accountregistratie en security te voorkomen.

---

## 20. Geplande implementatievolgorde

De aanbevolen ontwikkelvolgorde is:

### A. Nieuwe-account foundation

Doel:

- een reguliere nieuwe consument kan een account krijgen;
- een eigen huishouden ontstaat canoniek;
- de juiste beheercontext ontstaat zonder platform-/legacytrucs.

### B. Onboarding v2 — gebruiksdoel foundation

Doel:

- onboarding-state;
- eerste keuze **Inhuis halen / Wat Inhuis / Waar Inhuis**;
- server-side opslag;
- routing naar onboarding alleen waar terecht;
- bestaande huishoudens ongemoeid laten.

### C. Inhuis halen onboarding

Doel:

- minimale winkel-/bijna-op-inrichting;
- relevante defaults;
- geen verplichte exacte locaties.

### D. Wat Inhuis onboarding

Doel:

- aanwezigheid versus aantallen;
- geen of globale locatie;
- optionele koppeling naar Bijna op/Winkelen.

### E. Waar Inhuis onboarding

Doel:

- hoofdlocaties;
- optionele/gerichte sublocaties;
- Uitpakken en locatiebeheer aansluiten.

### F. Dynamische navigatie

Doel:

- alleen relevante capabilities prominent presenteren.

### G. Dynamische Instellingen

Doel:

- instellingen tonen op basis van autorisatie én productrelevantie.

### H. Circulair uitbreiden

Doel:

- centrale pagina **Wat wil je met Inhuis doen?**;
- nieuwe capabilities later activeren;
- alleen ontbrekende aanvullende vragen stellen.

### I. Echte uitnodigingen

Doel:

- veilige uitnodigings- en acceptatieflow voor nieuwe/existente accounts.

---

## 21. Eerste implementatieslice: gebruiksdoel foundation

Wanneer slice B wordt gestart, blijft de scope bewust klein.

### In scope

- canonieke keys:
  - `inhuis_halen`;
  - `wat_inhuis`;
  - `waar_inhuis`;
- huishoudgebonden onboarding-state;
- backend bepaalt of onboarding nodig is;
- frontendroute `/onboarding` of technisch equivalent;
- scherm **Waar wil je Inhuis mee beginnen?**;
- keuze server-side opslaan;
- hervatten/voltooien op een minimaal betrouwbaar niveau;
- bestaande huishoudens niet retroactief door onboarding sturen;
- canonieke permissions blijven leidend;
- relevante tests voor sessie, 401/403 en household isolation.

### Bewust niet in scope

- volledige dynamische navigatie;
- volledige dynamische Settings;
- voorraadtabellen breed wijzigen;
- locatieplicht technisch oplossen;
- kassabonbusinesslogica aanpassen;
- Gerechten aanpassen;
- uitgebreide bijna-op defaults;
- volledige accountregistratie als deze nog niet als aparte foundation gereed is;
- echte uitnodigingsflow;
- visuele herbouw van de hele app.

---

## 22. Acceptatieprincipes voor onboarding v2

Iedere implementatieslice moet ten minste bewaken dat:

1. de backend de autoriteit blijft voor identiteit, context en permissions;
2. een browser geen ander huishouden of productconfiguratie kan vervalsen;
3. 401 en 403 betekenisvol onderscheiden blijven;
4. `regular`, `system` en `none` contexten correct gescheiden blijven;
5. een Platformbeheerder geen gewone huishoudonboarding krijgt;
6. Superuser/IP-owner niet door een gewone consumentflow worden geprojecteerd;
7. een Lid niet zelfstandig structurele huishoudconfiguratie krijgt die zijn permission niet toestaat;
8. bestaande huishoudens niet onverwacht opnieuw moeten onboarden;
9. de keuze van een startprofiel geen nieuwe autorisatierol creëert;
10. latere uitbreiding mogelijk blijft zonder opnieuw de volledige onboarding te doorlopen.

---

## 23. Vastgestelde productbeslissingen

De volgende ontwerpkeuzes gelden als vastgesteld uitgangspunt voor deze lijn:

- Inhuis start **doelgericht**, niet feature-breed.
- De profielnamen zijn exact:
  1. **Inhuis halen**;
  2. **Wat Inhuis**;
  3. **Waar Inhuis**.
- De bijbehorende kernvragen zijn:
  - wat heb ik nodig?;
  - wat heb ik?;
  - waar ligt het?
- De eerste keuze is een startpunt en geen permanente beperking.
- Inhuis moet circulair kunnen uitbreiden.
- Alleen instellingen die voor het gekozen gebruik relevant zijn worden gevraagd/getoond.
- Exact locatiebeheer is niet voor iedere gebruiker verplicht.
- Rollen/permissions en productprofielen blijven strikt gescheiden.
- Het huishouden is de primaire eigenaar van gedeelde functionele inrichting.
- Bestaande huishoudens worden niet automatisch door nieuwe onboarding gedwongen.

---

## 24. Nog expliciet te specificeren vóór betreffende implementaties

Deze punten zijn richtinggevend besproken, maar vereisen per slice een expliciete technische/productbeslissing voordat code wordt aangepast:

1. **Nieuwe-account foundation**
   - registratiecontract;
   - e-mailverificatie indien gewenst;
   - moment van huishoudcreatie;
   - herstel/foutpaden.

2. **Voorraad zonder exacte locatie**
   - nullable locatie versus andere interne representatie;
   - migratie van bestaande records;
   - effecten op kassabon/uitpakken/voorraadqueries.

3. **Capability-opslag**
   - aparte tabel, JSON/configuratie of genormaliseerd model;
   - defaults en versiebeheer.

4. **Uitnodigingsflow**
   - tokenmodel;
   - expiratie;
   - bestaand versus nieuw account;
   - e-mailafhandeling.

5. **Definitieve navigatie per capability-combinatie**
   - welke items primair, onder Meer of verborgen zijn.

---

## 25. Referentie voor toekomstige chats en PR's

Bij toekomstige product- of implementatiebesprekingen kan naar dit document worden verwezen als:

> **`docs/product/INHUIS_PRODUCTONTWERP_ONBOARDING_V2.md`**

Gebruik daarbij dit principe:

- dit document beschrijft **productintentie en scope**;
- de actuele code en technische specificaties beschrijven **implementatiestatus**;
- als code en dit document uiteenlopen, is dat een signaal voor expliciete beoordeling, niet voor stille aanpassing van één van beide.

---

## 26. Wijzigingshistorie

| Datum | Versie | Wijziging |
|---|---|---|
| 2026-08-23 | 2.0 | Eerste canonieke versie. Doel-first onboarding, drie startprofielen, circulaire uitbreiding, inventarisatie van huidige repository en implementatievolgorde vastgelegd. |
