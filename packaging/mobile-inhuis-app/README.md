# Inhuis Android-testapp (native Jumbo en Lidl)

Dit is de reguliere Inhuis-website, geopend binnen een native Android-WebView,
met de bewezen Jumbo-webview uit Browserproef 0.1.10 (PR #733).
Het is **niet** dezelfde applicatie als Browserproef en gebruikt package-ID
`nl.inhuis.androidtest`. De huidige Docker-/desktop- en PWA-paden blijven intact.

De app accepteert uitsluitend de HTTPS-origin van een bestaande Inhuis-omgeving.
Bij het eerste openen wordt deze URL éénmaal ingevoerd (zonder path, query of
credentials); alleen de niet-geheime origin wordt bewaard. Een HTTP/Tailscale-IP
is opzettelijk niet toegestaan. Voor gebruik is dus een echte TLS-verbinding
met de Inhuis-backend vereist. De app verandert geen servers of certificaten.

Jumbo en Lidl worden geopend in de Capgo InAppBrowser met persistente WebView-data.
De programmatuur hergebruikt de geteste intern-router navigatie uit PR #733,
en stuurt alleen de bonpayload via een gebonden, tijdelijke brug naar de bestaande
Inhuis-batchverwerking. De backend controleert per write de Inhuis-gebruiker en
het actieve huishouden; een bevestigde bonqueue is geen volledig verwerkt bon.

Op expliciete PO-instructie is een vaste testsleutel voorlopig optioneel.
Als `INHUIS_ANDROID_TEST_KEYSTORE_B64` ontbreekt, gebruikt Gradle zijn standaard
Android-debugondertekening. Elke APK wordt nog op geldige ondertekening en
SHA-256 gecontroleerd. Verschillende builds kunnen verschillende certificaten
hebben; Android kan dan een update weigeren. Verwijder de bestaande app niet
automatisch: lokale appgegevens en winkelsessies kunnen verloren gaan.
Een aanwezige vaste secret moet geldig zijn; een ongeldige secret blijft een
buildfout. Commit nooit sleutels. Dit geldt alleen voor `nl.inhuis.androidtest`;
productieondertekening en Play Store-publicatie vereisen afzonderlijke PO-GO.

Risico: de eerste Jumbo-OAuth-redirect leverde in de browserproef eenmalig
een state-mismatch op. De herhaalde sessie werkte, maar die fout is nog niet
objectief verklaard. De oorspronkelijke cookie- en authbeveiliging blijven intact.
De winkelvoorwaarden en toestemming voor productie-import moeten apart worden
beoordeeld. Geen release/merge/deployment vanuit deze testbuild.


## AH en Lidl in de native Android-testapp

AH OAuth gebruikt op een via HTTPS geopende Tailscale Inhuis-host een **afzonderlijke
HTTPS-listener op poort 8443** met dezelfde betrouwbare Tailscale TLS-identiteit.
Deze listener reverse-proxyt uitsluitend naar de al bestaande lokale backend op
127.0.0.1:8011. De vertrouwde Inhuis HTTPS-listener op 443 blijft ongewijzigd.
De separate HTTPS-verbinding wordt veilig ingericht met
`scripts/po-tests/Inhuis_AH_HTTPS_8443_instellen.bat`; deze controleert eerst
bestaande Tailscale 443 en 8443 en wijzigt Docker of de database niet.
Tailscale Serve moet vóór de PO-test afzonderlijk beschikbaar worden gemaakt; het
wijzigen van Docker- of databasebindingen is niet nodig. Android staat geen
onbeveiligd HTTP toe, ook niet naar de eigen Tailscale-host. De backend weigert de
oude HTTP OAuth-link voor HTTPS-clients. AH-proxycookies zijn namespaced en
uitsluitend die cookies worden naar AH doorgestuurd. Tailscale certificaat- en
Android cleartext-beveiliging blijven verplicht.

Lidl gebruikt in de native Android-app voortaan de afzonderlijke Lidl WebView en
een tijdelijk, aan native browser-ID, request-ID, gebruiker en huishouden gebonden
transport. De bewezen Lidl-historieparser en bestaande centrale receipt-importqueue
worden ongewijzigd hergebruikt. Iedere bon heeft een queue-ACK; alleen de bestaande
backend-afronding van de volledige Lidl-historische import, ook bij een lege periode,
mag de native WebView sluiten en de onboardingstatus bijwerken. De normale
desktop-/browserroute met browserfavoriet blijft bestaan.

De bestaande native Jumbo-flow is de regressiebaseline. Er is geen automatische
merge, deployment, productiepublicatie of wijziging aan Docker-volumes voorzien.


## Android-packageversie

De CI genereert de native Android-app vanuit de Capacitor-template. De template
begint standaard met Android-versienaam 1.0. Het canonieke
`sync-android-version.mjs` past daarom na Capacitor sync **versionName en
versionCode in de gegenereerde Gradle-configuratie** aan op de geversioneerde
Android-package.json (voor 1.12.461 is versionCode 1120461). De APK-workflow
controleert de daadwerkelijke AndroidManifest-versienaam via de officiële aapt-tool.
Dit voorkomt dat de Android-installer een andere versie toont en maakt een
correcte versiecode-volgorde mogelijk. Installatie over een bestaande app is
nog steeds afhankelijk van een overeenkomende ondertekeningssleutel.
