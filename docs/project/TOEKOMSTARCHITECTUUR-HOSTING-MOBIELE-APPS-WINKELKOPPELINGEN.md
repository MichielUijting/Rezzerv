# Toekomstarchitectuur: hosting, Android/iOS en winkelkoppelingen

**Status:** vastgelegd toekomstontwerp, **geen** opdracht tot implementatie, hosting, migratie of release.
**Vastgelegd:** 23 november 2026.
**Huidige gecontroleerde basis:** Inhuis `main` 1.12.445, na PR #725 en #726. Dit is een momentopname; actuele branch, configuratie en tests blijven de operationele waarheid.
**TEST_LEVEL_PROVISIONAL: S** — deze wijziging is uitsluitend documentatie.

## 1. PO-besluit en afbakening

Inhuis moet later beschikbaar kunnen zijn als gehoste dienst met een centrale database en gebruikersapps voor Android en iOS uit de appstores, naast toegang via het web. Reguliere gebruikers mogen dan geen Tailscale, lokaal IP-adres, laptop of eigen server nodig hebben. Een gebruiker koppelt winkels vanuit Inhuis; toegestane historische en toekomstige aankopen kunnen daarna centraal worden verwerkt, met huishoudspecifieke voorraad en voorspellingen. Het gewenste proces vergt zo min mogelijk handmatige begeleiding en geen noodzakelijke betaalde AI-licenties.

**Nu blijft de prioriteit uitsluitend de huidige Inhuis-oplossing** op de ontwikkel-/server-laptop, met de bestaande Docker/PostgreSQL-start via `start.bat`, Tailscale voor de huidige mobiele testtoegang, en de bestaande winkelkoppelingen. Dit document verandert **geen** gedrag, endpoints, configuratie, database, loginroute, app-bundel, scanfunctionaliteit, importlogica, toestemmingen of gebruiksgegevens. Het autoriseert geen aankoop van hosting, provider-toegang, deployment of publicatie.

Een doelarchitectuur is **niet** hetzelfde als een bestaande voorziening of een bewezen overeenkomst met AH, Lidl of Jumbo. De huidige functionaliteit en securitycontracten uit `AGENTS.md`, `docs/project/ARCHITECTURE-AND-DATA.md`, `docs/project/SECURITY-AND-HOUSEHOLD-ISOLATION.md` en `docs/technical/TECHNISCH-ONTWERP.md` behouden voorrang.

## 2. Huidige werkelijkheid — geen productieclaims

| Onderdeel | Huidige implementatie (1.12.445) | Nog niet bewezen voor gehoste native apps |
| --- | --- | --- |
| Inhuis zelf | React/Vite, FastAPI, PostgreSQL 17, Docker Compose, browserinterface, huishoudisolatie | Publieke HTTPS-hosting, native storepakketten, schaalbaarheid en productiebeheer |
| Mobiele toegang | Browser via LAN/Tailscale naar de actuele Inhuis-machine | Toegang via publiek domein zonder VPN |
| Albert Heijn | Huishoudgebonden connect-/callbackroute en versleutelde AH-sessie; tijdelijke AH-browserproxy; na PR #725 verbeterde mobiele callback | Praktische end-to-end-validatie in Android/iOS-storeapp, robuuste multi-instance-state en formeel ondersteunde winkelautorisatie |
| Lidl | Browser-/JavaScript-overdracht vanuit Lidl-aankoopgeschiedenis, onder andere via `window.opener` en `postMessage` | Betrouwbare native-appoverdracht, achtergrondtoegang en een toegestane duurzame providerintegratie |
| Jumbo | Browsergebaseerde POC/bookmarklet voor bestelgeschiedenis en import | Bewezen, toegestane automatische koppeling voor Android en iOS |
| Achtergrondverwerking | Bestaande huishoudgebonden importservices; AH-achtergrondsync met beheerde featureflag, onderhoudsvenster en PostgreSQL-advisory lock | Een volledig uitgewerkte centrale worker-/schedulerarchitectuur met onafhankelijk beheer en monitoring |
| Opslag | Huidige PostgreSQL en huidige Docker-volumes, inclusief bronbonnen en winkelgegevens | Gehoste back-ups, disaster recovery, opslagmigratie en operationeel gegevensbehoud |

**Bronnen in de code:** `backend/app/api/receipt_ah_oauth_proxy_routes.py`, `backend/app/api/retailer_receipt_routes.py`, `backend/app/services/ah_receipt_background_sync.py`, `frontend/src/features/storeConnections/StoreConnectionsPage.jsx`, `lidlWebReceiptBridge.js` en `jumboReceiptPocBridge.js` in dezelfde frontendmap.

De huidige AH-proxy gebruikt de door AH aangeleverde `appie://login-exit`-stroom en herschrijft de terugkeer naar een kortlevende Inhuis-callback. De browserlogin kan een speciale installatie-ID en Next.js-redirectverwerking vereisen. Dit is **geen bewijs van een voor Inhuis officieel geregistreerde OAuth-client**. De flowstatus staat op dit moment in procesgeheugen, heeft een korte geldigheidsduur en vervalt bij een backendherstart; dat is geen voltooide multi-instance-oplossing. De huidige mobiele AH-praktijkproef mag niet als geslaagd worden beschreven voordat deze daadwerkelijk door de PO is doorlopen.

## 3. Logische doelarchitectuur (later, niet nu)

```text
  Android-app          iOS-app             Webbrowser
       |                   |                    |
       +-------------------+--------------------+
                           |
                  Publieke HTTPS-toegang
                 (vast Inhuis-domein; TLS)
                           |
              Applicatie-ingang/API-router
                           |
                 Inhuis FastAPI-backend
                 |                  |
       Accounts, sessies,     Koppel-/importservices
       huishoudautorisatie   per winkel (provider-adapters)
                 |                  |
                 +--------+---------+
                          |
              Huishoudgebonden importqueue
                          |
              Afzonderlijke achtergrondwerker
                          |
             Bestaande bon- en voorraadketen
                          |
                 Centrale PostgreSQL
                          |
            Beveiligde bon-/objectopslag
```

Dit zijn **logische verantwoordelijkheden**, geen keuze voor een specifieke cloud, microservices, Kubernetes, nieuwe database of technische hostingpartij. De huidige FastAPI-services en bestaande import-/voorraadcontracten blijven de basis. Een gehoste uitvoering moet dezelfde household/object/role-autorisatie server-side behouden; een client of winkelcallback mag geen vrij huishouden kiezen.

Het publieke HTTPS-domein, de app-identiteit en de centrale backend vormen één stabiel systeem. De mobiele app kan in een latere afweging bestaande React-schermen hergebruiken via een geschikte native container, of gerichte native schermen krijgen. **Er is nog geen keuze voor Capacitor, React Native of een volledig native herschrijving**, en appstoregoedkeuring is niet aangenomen.

## 4. Twee gescheiden aanmeldprocessen

**A. Inhuis-account en huishouden.** De gebruiker meldt zich aan bij Inhuis. De backend stelt de identiteit, rollen en toegestane huishoudcontext vast. Voorraad en kassabonnen zijn nooit globaal gedeelde gebruikersdata. Na accountverwijdering blijven de contracten voor gedeelde huishoudgegevens en beheerderoverdracht intact.

**B. Winkel koppelen.** Een bevoegd lid kiest in het bestaande Winkelkoppelingen-/onboardingproces AH, Lidl of Jumbo. Inhuis creëert een huishoudgebonden, kortlevend koppelverzoek. De gebruiker doorloopt een door de winkel toegestane aanmelding, bij voorkeur met een systeembrowser. De backend valideert de terugkeer en bewaart uitsluitend toegestane, versleutelde sessie-/koppelgegevens. Een nieuwe status `gekoppeld` verschijnt **uitsluitend nadat de backend de koppeling bevestigt**; een browserterugkeer of geopend aanmeldvenster is daarvoor onvoldoende.

Voor toekomstige native terugkeer is een geverifieerde Inhuis-HTTPS-link met **Android App Links / iOS Universal Links** de voorkeursrichting. Dit gaat alleen over het terugbrengen naar de eigen Inhuis-app en is **niet** automatisch een door een winkel geaccepteerde redirect-URI. Voor iedere provider moeten toegestane clientidentiteit, redirect-URI, toestemming en technische ondersteuning onafhankelijk worden vastgesteld.

Een eventuele code-/tokenuitwisseling gebeurt alleen volgens een daadwerkelijk toegestane providerflow; waar toepasselijk gebruiken we een server-side uitwisseling met eenmalige state, nonce en geschikte PKCE-regels. Auth-codes of tokens komen nooit in deep links, querylogs, analytics, screenshots of gedeelde foutmeldingen terecht. Bij mislukken, annuleren, time-out of herstart volgt een duidelijke hersteloptie zonder schijnkoppeling.

## 5. Providergrenzen: AH, Lidl, Jumbo

### Albert Heijn

- **Huidig behouden:** de bestaande household-scoped AH-koppeling, callback, versleutelde opslag en bonverwerking.
- **Later ontwerpen:** een stabiele externe HTTPS-omgeving, expliciet toegestane AH-autorisatie en een veilige Inhuis-terugkeer. De huidige `appie://`-vertaling is een *compatibiliteitsmechanisme*, niet het gewenste onvoorwaardelijke productiecontract.
- **Blokkerend bewijs:** toestemming/voorwaarden en praktische Android- én iOS-proef (inloggen, eventuele captcha, callback, backendstatus, bonnen ophalen, fout-/annuleerpad). Er mag niet worden aangenomen dat AH een openbare API of officiële Inhuis-client ondersteunt.
- **Multi-instance:** korte flowstatus moet later centraal, tijdgebonden, eenmalig consumeerbaar en gebonden aan account/sessie/huishouden worden opgeslagen. Bij uitval blijft de gebruiker veilig herstartbaar; geen gedeelde procesdictionary als schaalbaar contract.

### Lidl

- **Huidig behouden:** browseroverdracht met een door gebruiker bezochte Lidl-pagina en import via het bestaande Inhuis-contract.
- **Later onderzoeken:** een door Lidl ondersteunde machtiging of gegevensuitwisseling. De huidige `window.opener`, `postMessage` en paginagebonden JavaScript zijn **niet** zonder meer overdraagbaar naar een native app of achtergrondtaak.
- **Zonder toegestane automatische toegang:** bied alleen een expliciete, gebruiksvriendelijke gebruikersimport van beschikbare digitale bonnen/bestanden aan; presenteer deze niet als automatische winkelkoppeling.

### Jumbo

- **Huidig behouden:** de bestaande browsergebaseerde POC en handmatige/geverifieerde import.
- **Later onderzoeken:** aantoonbaar toegestane providerintegratie; een POC/bookmarklet is geen bewijs van een onderhoudbare achtergrondkoppeling.
- **Zonder toegestane automatische toegang:** veilige, door gebruiker geïnitieerde bonimport met correcte statusweergave. Geen claim over automatische synchronisatie.

**Voor alle winkels:** geen credentials of browsercookies via een andere gebruiker of een ander huishouden; geen ongevraagde scraping, omzeiling van providerbeveiliging of aanname dat toegangsvoorwaarden dit toestaan. Winkels kunnen hun login of gegevensstructuur wijzigen. Functionele beschikbaarheid is daarom per provider, platform en importmodus aantoonbaar.

## 6. Backendgrenzen, gegevensbehoud en security

1. **Eén API-contract voor web en native.** Hergebruik bestaande FastAPI-endpoints en de centrale receipt-/import-/inventory-services. Appspecifieke handoff blijft aan de rand; businessregels en household-autorisatie blijven server-side.
2. **Autorisatie vóór koppelactie.** Een winkelkoppeling is aan de geautoriseerde huidige account-/huishoudcontext gebonden. De gebruiker kan geen andere `household_id`, een andere winkelverbinding of een importbatch claimen via clientvelden.
3. **Status gescheiden houden.** `Koppeling aangevraagd`, `autorisatie voltooid`, `gekoppeld`, `historie in wachtrij`, `geïmporteerd` en `mislukt` zijn verschillende feiten. Geen automatische succesmelding bij alleen een terugkeer uit de browser.
4. **Centrale achtergrondtaken.** Alleen toegestane synchronisaties worden met idempotentie, een uniek huishoud-/provideranker, checkpoints, limieten, gecontroleerde retries, audit en backoff verwerkt. De telefoon hoeft niet open te blijven. De bestaande PostgreSQL-lock en featureflags zijn vertrekpunt, geen vervanging voor ontworpen hosting-orchestratie.
5. **Secrets en data.** Winkelautorisaties zijn versleuteld en krijgen beperkt toegangsniveau. Geen winkelwachtwoorden in de app/serverlogs. PostgreSQL en bon-/objectbestanden krijgen afzonderlijke toegangs- en backupregimes. Versleutel transport en opslag passend, minimaliseer retentie en scheid huishoudens.
6. **Gegevens verwijderen.** Bestaande accountverwijderings- en household-behoudcontracten gelden ook in cloudopslag, achtergrondtaken, exports en back-ups. Wettelijk noodzakelijke bewaring en backupverwijdertermijnen moeten vóór productie worden uitgewerkt.
7. **Beveiligde publieke rand.** HTTPS en eigen domein, toegestane origins/callback-allowlists, veilige cookies/session handling, anti-CSRF/state, rate limiting, secretsbeheer, audit zonder tokens, en geen willekeurige proxy van webpaden op het publieke hoofddomein.
8. **Beschikbaarheid en herstel.** Meerdere API-instanties mogen geen koppelstatus verliezen of dubbel importeren. Definieer migratie-/schema-authority, backups, restores, health/monitoring, incidentafhandeling en rollback afzonderlijk voordat gehoste productie begint.
9. **Privacy en voorwaarden.** Voor consumentenhosting afzonderlijk toetsen: AVG-grondslag, verwerkersovereenkomsten, opslaglocatie, dataminimalisatie, toestemming en voorwaarden van elke winkelketen. Geen inhoudelijke goedkeuring in dit document geïmpliceerd.

## 7. Fasering en bewijspoorten — zonder huidige koers te wijzigen

| Fase | Moment | Oplevering en acceptatie |
| --- | --- | --- |
| **0. Huidige oplossing** | **Nu** | Docker/`start.bat`, ontwikkel-/server-laptop en Tailscale blijven; gerichte praktijkproeven voor de huidige AH/Lidl/Jumbo-flow en accountverwijdering. Geen nieuwe cloud/native technische werkzaamheden door deze PR. |
| 1. Hostingspecificatie | Latere afzonderlijke PO-opdracht | Provider-/kostenkeuze, eigen domein, HTTPS, logging, backups/restore, geheimenbeheer, veilige opslag, migraties en householdisolatie, met acceptatietests. |
| 2. Mobiele appschil | Latere afzonderlijke PO-opdracht | Native packagingkeuze, Android/iOS-browserlogin en app-return, platformrechten, deep-linkbeveiliging, appstoretoetsing en handmatige bonimport. |
| 3. Winkeladapter per provider | Latere afzonderlijke PO-opdracht | Alleen met aantoonbaar ondersteunde/toegestane providerroute; anders een expliciete handmatige importfallback. Echte eindproef per winkel en platform, inclusief annuleren en verlopen aanmeldingen. |
| 4. Opslag- en accountmigratie | Afzonderlijke PO-opdracht + databeschermingsplan | Objectieve identificatie van actuele data, geverifieerde backups en terugzetproef, migratieplan, behoud gedeelde huishouddata en gecontroleerde proefmigratie. |
| 5. Productie en publicatie | **Alleen afzonderlijke expliciete PO-GO** | Deployment, DNS-omschakeling, daadwerkelijke appstorepublicatie, monitoring, nazorg. Een PR-merge is hiervoor geen toestemming. |

### Beslissingen die bewust open blijven

- Hostingpartij, geografische locatie, capaciteit, kosten en operationeel beheer.
- Exact publiek domein en app-identifiers.
- Android/iOS-techniek (native container versus aparte native frontend).
- Per winkel: officiële/toegestane autorisatie, zakelijke toestemming, haalbaarheid van historie en toekomstig automatisch ophalen.
- Arbeids- en onderhoudslast van winkelintegraties versus handmatige import.
- Beleid voor offline gebruik, appstorebeleid, privacydocumenten en bewaartermijnen.

**Geen van deze open beslissingen blokkeert de huidige Tailscale-/Docker-ontwikkeling.** Een latere implementatie vereist een nieuwe, duidelijk afgebakende PR en test-/acceptatieopdracht.

## 8. Acceptatie van deze documentatie-PR

- [ ] De huidige werking en het toekomstontwerp zijn expliciet gescheiden.
- [ ] AH, Lidl en Jumbo zijn technisch realistisch als **nog te valideren** providerintegraties beschreven.
- [ ] Huishoudisolatie, rechten, importidentiteit, data- en bronbonbehoud blijven bindend.
- [ ] Geen runtime-/frontend-/backend-/database-/Docker-/CI-/versiewijzigingen.
- [ ] Geen hostingaanvraag, deployment, appstorepublicatie of productieomschakeling.
- [ ] Alleen documentatiechecks en de volgens risico/classifier toepasselijke GitHub-gates; merge uitsluitend na expliciete PO-GO.
