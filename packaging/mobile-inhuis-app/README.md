# Inhuis Android-testapp (native Jumbo)

Dit is de reguliere Inhuis-website, geopend binnen een native Android-WebView,
met de bewezen Jumbo-webview uit Browserproef 0.1.10 (PR #733).
Het is **niet** dezelfde applicatie als Browserproef en gebruikt package-ID
`nl.inhuis.androidtest`. De huidige Docker-/desktop- en PWA-paden blijven intact.

De app accepteert uitsluitend de HTTPS-origin van een bestaande Inhuis-omgeving.
Bij het eerste openen wordt deze URL éénmaal ingevoerd (zonder path, query of
credentials); alleen de niet-geheime origin wordt bewaard. Een HTTP/Tailscale-IP
is opzettelijk niet toegestaan. Voor gebruik is dus een echte TLS-verbinding
met de Inhuis-backend vereist. De app verandert geen servers of certificaten.

Jumbo wordt geopend in de Capgo InAppBrowser met persistente WebView-data.
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
