# Inhuis — geïsoleerde Android-winkelbrowserproef

TEST_LEVEL_PROVISIONAL: L — nieuw native packaging- en CI-pad; derde-partijbrowser met beveiligingsgrenzen.
STYLEGUIDE_IMPACT: isolated test harness only; no production UI change.

Doel: aantonen of de gebruiker zonder bladwijzer in een zichtbare ingebouwde browser bij Jumbo en Lidl kan aanmelden, naar de eigen historie kan gaan en een minimaal read-only DOM-signaal naar de app kan teruggeven. Deze eerste proef verzamelt geen boninhoud en bewijst geen aanmelding, complete historie, permanente koppeling of toegestane automatische import.

- Eigen Android app-ID `nl.inhuis.browserprobe`, geen Inhuis-account, geen API of PostgreSQL, geen wijzigingen aan bestaande app of PWA.
- Capacitor 8.6.0 (MIT), Capgo InAppBrowser 8.27.9 (MPL-2.0), esbuild 0.25.12 (MIT). Geen betaalde Capgo-service of AI nodig. Bron: https://github.com/ionic-team/capacitor/tree/8.6.0 en https://github.com/Cap-go/capacitor-inappbrowser/tree/8.27.9. Bibliotheken worden niet gewijzigd of gekopieerd. Distributielicenties en dependency-lock/audit nog beoordelen voordat dit een productiecomponent wordt.
- De test gebruikt alleen de officiële winkelpagina's uit de bestaande Inhuis-integratie. Geen aangepaste user agent, logininjectie, cookie-/tokenexport, wachtwoordinspectie, proxy, screenshot of TLS-omzeiling. Native bridge beperkt tot één exacte winkel-origin; de scriptguard controleert bovendien de geschiedenisroute. Onverwachte origins ontvangen geen resultaat. De probe behandelt een signaal nooit als authenticatiebewijs.
- Geen gegevens schrijven naar Inhuis of winkelaccount; normaal aanmelden op de winkelwebsite zelf, alleen de weergegeven historie observeren. Indien de website embedded login weigert, stop en rapporteer. Niet omzeilen. Toestemming voor daadwerkelijke geautomatiseerde bonimport is nog niet vastgesteld.
- De app houdt uitsluitend tijdelijke booleans in geheugen. Winkel-WebView kan zelf normale sessiecookies bewaren; gebruik bij voorkeur een eigen testaccount, deel geen wachtwoorden/screenshots met persoonsgegevens en verwijder appgegevens na de proef.
- PR #570 betreft Windows standalone packaging en levert geen native mobiele basis. PR #732 bevat de bestaande winkelimport, maar is geen dependency van deze geïsoleerde eerste proef.

## Android-build

GitHub Actions `Android winkelbrowser haalbaarheidsproef` genereert in de geïsoleerde submap het Capacitor Android-project en een debug-APK. Node 22, JDK 21 en Android SDK 36. APK en de tijdens de build gegenereerde package-lock worden als tijdelijke CI-artefacten aangeboden; geen appstorepublicatie of release. Directe dependencies zijn exact gepind; transitieve lock wordt bij eerste build gegenereerd omdat het huidige ontwikkelmilieu geen npm-toegang heeft. Dit is nog geen reproduceerbare productiebuild.

## Praktijkproef

1. Installeer uitsluitend de afzonderlijke test-APK nadat de build en dependencybeoordeling zijn geslaagd.
2. Open Jumbo; meld je op de echte winkelpagina aan. Ga naar de historie, controleer visueel of je eigen bonnen zichtbaar zijn. Sluit het browservenster via de normale sluitknop.
3. De testapp toont of een beveiligd historiesignaal terugkwam. Een route alleen, zonder herkenbare inhoud, is geen bewijs dat bonnen toegankelijk zijn.
4. Herhaal voor Lidl. Controleer ook annuleren, verkeerde inlog en terugkeer.
5. Leg alleen per winkel vast: login mogelijk ja/nee, bonnen zichtbaar ja/nee, historiesignaal ja/nee, terugkeer ja/nee. Geen bongegevens of credentials delen.

Vervolg na bewijs: per provider voorwaarden/technische toegang toetsen, bestaande importadapter op native transport aansluiten, echte queue-ACK, huishoudautorisatie en idempotentie testen. iOS afzonderlijk bewijzen. Geen productie- of releaseactie zonder PO-GO.
