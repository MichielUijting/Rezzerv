# Open-source-licenties — geïsoleerde Android-browserproef

Deze experimentele app bevat ongewijzigde open-sourcecomponenten. De exacte npm-resoluties en integriteitshashes staan in `package-lock.json`. Een volledige actuele dependency-audit draait in GitHub Actions.

- `@capacitor/core`, `@capacitor/android`, `@capacitor/cli` 8.6.0 — MIT. Bron: https://github.com/ionic-team/capacitor/tree/8.6.0
- `@capgo/capacitor-inappbrowser` 8.27.9 — Mozilla Public License 2.0 (MPL-2.0). De oorspronkelijke, ongewijzigde broncode is beschikbaar via https://github.com/Cap-go/capacitor-inappbrowser/tree/8.27.9 . Licentietekst: https://www.mozilla.org/en-US/MPL/2.0/ . De app claimt geen eigendom van deze code of andere rechten dan de bijbehorende open-sourcelicentie.
- `esbuild` 0.25.12 — MIT (build-time). Bron: https://github.com/evanw/esbuild/tree/v0.25.12

De dependency-lock bevat ook indirecte packages met MIT-, ISC-, Apache-2.0-, Unlicense-, 0BSD- en BlueOak-1.0.0-licenties. De oorspronkelijke licentieteksten en broncode van de betreffende packages blijven onder hun eigen voorwaarden beschikbaar. Geen Capgo Cloud/SDK-abonnement, betaalde API of AI-licentie gebruikt.

**Beperkingen**: een geldige open-sourcelicentie is geen winkeltoestemming, geen veiligheidskeurmerk en geen recht om kassabonnen geautomatiseerd bij Jumbo of Lidl te importeren. De proefapp slaat geen bongegevens in Inhuis op; een ingesloten Android WebView kan wel cookies/sessiegegevens bijhouden. Wis na afloop appgegevens en verwijder de proefapp.
