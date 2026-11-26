# Inhuis — geïsoleerde Android-winkelbrowserproef

TEST_LEVEL_PROVISIONAL: L — nieuw native packaging- en CI-pad; derde-partijbrowser met beveiligingsgrenzen.
STYLEGUIDE_IMPACT: isolated test harness only; no production UI change.

Doel: aantonen of de gebruiker zonder bladwijzer in een zichtbare ingebouwde browser bij Jumbo en Lidl kan aanmelden, naar de eigen historie kan gaan en een minimaal read-only DOM-signaal naar de app kan teruggeven. Deze eerste proef verzamelt geen boninhoud en bewijst geen aanmelding, complete historie, permanente koppeling of toegestane automatische import.

- Eigen Android app-ID `nl.inhuis.browserprobe`, geen Inhuis-account, geen API of PostgreSQL, geen wijzigingen aan bestaande app of PWA.
- Capacitor 8.6.0 (MIT), Capgo InAppBrowser 8.27.9 (MPL-2.0), esbuild 0.25.12 (MIT). Geen betaalde Capgo-service of AI nodig. Bron: https://github.com/ionic-team/capacitor/tree/8.6.0 en https://github.com/Cap-go/capacitor-inappbrowser/tree/8.27.9. Bibliotheken worden niet gewijzigd of gekopieerd. De vastgelegde transitieve npm-dependencies staan in `package-lock.json`; MPL-bron en licentiekennisgeving staan in `OSS-NOTICES.md`. Hergebruik voor productie vereist een nieuwe afzonderlijke veiligheids- en juridische toets.
- De test gebruikt alleen de officiële winkelpagina's uit de bestaande Inhuis-integratie. Geen aangepaste user agent, logininjectie, cookie-/tokenexport, wachtwoordinspectie, proxy, screenshot of TLS-omzeiling. Native bridge beperkt tot één exacte winkel-origin; de scriptguard controleert bovendien de geschiedenisroute. Onverwachte origins ontvangen geen resultaat. De probe behandelt een signaal nooit als authenticatiebewijs.
- Geen gegevens schrijven naar Inhuis of winkelaccount; normaal aanmelden op de winkelwebsite zelf, alleen de weergegeven historie observeren. Indien de website embedded login weigert, stop en rapporteer. Niet omzeilen. Toestemming voor daadwerkelijke geautomatiseerde bonimport is nog niet vastgesteld.
- De app houdt uitsluitend tijdelijke booleans in geheugen. De proef staat normale WebView-sessieopslag toe vanaf 0.1.1; Android kan winkelcookies bewaren. gebruik bij voorkeur een eigen testaccount, deel geen wachtwoorden/screenshots met persoonsgegevens en verwijder appgegevens na de proef.
- PR #570 betreft Windows standalone packaging en levert geen native mobiele basis. PR #732 bevat de bestaande winkelimport, maar is geen dependency van deze geïsoleerde eerste proef.

## Android-build

GitHub Actions `Android winkelbrowser haalbaarheidsproef` genereert in de geïsoleerde submap het Capacitor Android-project en een debug-APK. Node 22, JDK 21 en Android SDK 36. De volledige npm-lock is gecommit en de build gebruikt uitsluitend `npm ci`; een GitHub Actions `npm audit --audit-level=high` moet slagen. De workflow publiceert tijdelijk een debug-APK, APK-SHA256 en dependency-lock als aan een commit gebonden artefact. Dit is geen officiële productierelease, appstorepublicatie of bewijs van echte winkel-login.

## Praktijkproef

1. Installeer uitsluitend de afzonderlijke test-APK nadat de build en dependencybeoordeling zijn geslaagd.
2. Open Jumbo; meld je op de echte winkelpagina aan. Ga naar de historie, controleer visueel of je eigen bonnen zichtbaar zijn. Sluit het browservenster via de normale sluitknop.
3. De testapp toont of een beveiligd historiesignaal terugkwam. Een route alleen, zonder herkenbare inhoud, is geen bewijs dat bonnen toegankelijk zijn.
4. Herhaal voor Lidl. Controleer ook annuleren, verkeerde inlog en terugkeer.
5. Leg alleen per winkel vast: login mogelijk ja/nee, bonnen zichtbaar ja/nee, historiesignaal ja/nee, terugkeer ja/nee. Geen bongegevens of credentials delen.

Vervolg na bewijs: per provider voorwaarden/technische toegang toetsen, bestaande importadapter op native transport aansluiten, echte queue-ACK, huishoudautorisatie en idempotentie testen. iOS afzonderlijk bewijzen. Geen productie- of releaseactie zonder PO-GO.

## 0.1.1 – fysieke PO-proef vervolg
Open eerst de officiële publieke winkelhomepage en meld je zelf aan. Sluit het venster en kies daarna de afzonderlijke bonhistorieknop. Normale WebView-sessieopslag blijft voor deze proef toegestaan om de aanmelding tussen beide stappen te behouden; geen cookies/tokens worden door Inhuis gelezen of geëxporteerd. Wis na afloop de gegevens van uitsluitend de proefapp. Geen brug tijdens de aanmeldfase, alleen de bestaande exact-origin/route-guard tijdens historie. Geen omzeiling van providerbeveiliging. Een terugkeer uit de winkel bewijst geen login. Bij een blokkade door Play Protect/Norton niet doorgaan of beveiliging uitschakelen.

## 0.1.2 – Jumbo same-window proef
PO meldt Lidl 0.1.1 volledig geslaagd en Jumbo foutpagina bij heropenen van /bestellingen; Chrome redirect naar /orders. Jumbo opent de officiële homepage; de gebruiker navigeert zelf via Mijn Jumbo naar Bestellingen binnen hetzelfde venster. Geen afzonderlijke Jumbo-historieknop. Exacte HTTPS-routes /bestellingen en /orders toegestaan voor uitsluitend read-only boolean historieprobe; geen injectie op login of andere routes. De native bridge is tijdens het gecombineerde Jumbo-venster beperkt tot de Jumbo-origin; acceptatie blijft beperkt tot exacte historie, nonce en view-ID. Alleen booleans voor route bereikt, pagina geladen en scriptfout worden gerapporteerd, geen volledige URL of persoonlijke gegevens. Lidl-flow ongewijzigd. Werkelijke Jumbo-aanmelding en historie nog te bewijzen. Geen omzeiling van beveiliging. TEST_LEVEL_PROVISIONAL: L.

## 0.1.3 — automatische Jumbo-navigatie
PO bevestigt eigen bonnen zichtbaar na handmatige navigatie op 0.1.2. De proef zoekt uitsluitend zichtbare uitlogbediening en de officiële Bestellingen-link in dezelfde Jumbo-origin, niet op loginpagina's of bij zichtbare wachtwoordvelden. Eén navigatiepoging via die link, geen credentialinspectie of API-verzoek. Bij ontbrekende markers blijft handmatige navigatie mogelijk. Automatisch sluiten uitsluitend na geldig historie-markerbericht. DOM-selectors zijn hypothesen, nog niet fysiek bewezen. De bestaande GraphQL-import is onderzocht maar bewust niet uitgevoerd: deze proef verzamelt geen bondata en provider-toestemming voor import is nog niet vastgesteld. Lidl-flow behouden. TEST_LEVEL_PROVISIONAL: L.
