# AH-klantkaartkoppeling — afronding en acceptatie (10 oktober 2026)

Status: opdracht door PO bevestigd. Implementatie en functionele validatie nog open.
Voorlopig risico: **L**, wegens authenticatie, financiële kassabonverwerking, huishoudisolatie en ontvangstketen.

## Af te ronden functionele eisen
1. Bij openen van Kassa worden voor een gekoppeld huishouden uitsluitend nieuwe AH-bonnen opgehaald, zonder dubbele opslag.
2. De handmatige actie **Nu synchroniseren** werkt en geeft resultaat en eventuele fouten begrijpelijk weer.
3. Datum, winkel, artikelregels, aantallen, eenheidsprijzen en bonbedragen worden met de AH-bron gereconcilieerd.
4. Een tweede sync na succesvolle eerste sync importeert nul doublures; gedeeltelijke uitval is veilig herhaalbaar.
5. Accounttokens blijven versleuteld, buiten logs/UI en gebonden aan het juiste huishouden; herstart behoudt koppeling.
6. AH-inloggen verloopt via browser en automatische callback, zonder autorisatiecode te kopiëren.
7. Diagnoseer de historische uitkomst **99 van 100** zonder te veronderstellen dat de 100e ontbreekt: onderscheid *reeds bekend*, *buiten limiet*, *detailfout* en *importfout*. Houd bon-ID's en accountgegevens buiten publieke rapportage.
8. Tijdens sync is begrijpelijke voortgang zichtbaar (aantal gevonden, verwerkt, overgeslagen en mislukt). Fout betekent nooit stilzwijgend succes.
9. Test de UAC-vrije `ah-login.127-0-0-1.sslip.io`-route op geen beheerdersprompt, werkende hCaptcha, automatische terugkeer en zichtbare bonnen in Kassa.
10. Vergelijk AH-kortingen, bon- en regeltotalen en betalingen; kortingen of betaalmiddelen worden nooit fysieke voorraad.

## Voorlopige technische bevindingen uit main
- `backend/app/integrations/retailer_accounts/ah.py` leest standaard maximaal 100 bonoverzichten via één API-page; pagination en paginabeperking verdienen controle.
- `backend/app/services/ah_receipt_sync_service.py` kent per-bon foutverzameling en bewaart geslaagde receipt IDs als bekend; de actuele oorzaak van 99/100 is hiermee nog **niet** bewezen.
- AH is een ongedocumenteerde externe API; netwerk-, account- en captcha-afhankelijkheden kunnen lokaal functioneel bewijs vereisen.
- De handoff van gemergede PR #555 staat in `docs/project/PR555-AH-OAUTH-HANDOFF.md`.

## Veiligheid / scope
- Geen wijzigingen aan gebruikersdata, secrets, bestaande volumes of hosts-bestand op basis van aannames.
- Bestaande account-/huishoud- en ontvangstcontracten blijven leidend; geen parser- of databasearchitectuur-refactor zonder bewezen noodzaak.
- Testen met gesynthetiseerde financiële bonnen, geen echte klant-/kassabondata naar GitHub.
- Gewone lokale PO-test: bewezen veilig scriptpatroon; schone werkmap, non-destructieve fast-forward en exacte kandidaat-SHA; daarna de bestaande `start.bat`.

## Verificatie en oplevering
- Eerst gerichte diagnose en contracttests; vervolgens implementatie, frontend build en relevante ontvangst-/security-/ketenchecks.
- Finale patchversie + versiesync pas als de code definitief is; F7/exact-candidate uitsluitend op finale SHA.
- PR blijft Draft tot vereiste checks en functionele acceptatie kloppen. Merge alleen na expliciete PO-GO voor exacte SHA; release afzonderlijk.
