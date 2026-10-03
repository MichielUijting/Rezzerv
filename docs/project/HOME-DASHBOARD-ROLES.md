# Inhuis dashboard en rollen — implementatiescope

Status: taakscope voor de nieuwe landingspagina en vereenvoudigde gebruikersrollen.

## Rollen

Gebruikerszichtbaar gelden voor deze taak:
- **Gebruiker** — reguliere huishoudgebruiker;
- **Beheerder** — beheer van het eigen huishouden;
- **Frontteamlid** — aanvullende platformrol bovenop Gebruiker of Beheerder;
- **Platformbeheerder** — support en technisch platformbeheer;
- **Superuser** — functioneel platformbeheer;
- **IP-eigenaar** — beschermde eigenaarsrol die uitsluitend Superusers kan aanstellen en deactiveren.

Interne technische role keys mogen behouden blijven wanneer dat voor compatibiliteit noodzakelijk is. De gebruikerszichtbare terminologie volgt bovenstaande namen.

## Landingspagina

De mobiele landingspagina is geen tweede hoofdmenu meer. De centrale onderste actiebalk blijft de primaire navigatie. De landingspagina wordt een dagelijks/wekelijks dashboard voor Gebruiker, Beheerder en Frontteamlid.

### Compacte statusregel

Bovenaan staan drie volledig klikbare statussen:
1. **Meldingen** — aantal open/ongelezen meldingen; opent Meldingen;
2. **Boodschappen** — aantal artikelen op de actuele boodschappenlijst; opent Boodschappen;
3. **Nog opbergen** — aantal artikelen dat nog vanuit Kassa/Uitpakken naar Voorraad moet; opent de relevante verwerkingsflow.

### Dashboardtegels met drill-down

1. **Uitgaven t.o.v. vorig jaar**
   - uitgaven over de laatste 4 gekozen perioden;
   - vergelijking met exact dezelfde perioden een jaar eerder;
   - huidige periode donkergroen, dezelfde periode vorig jaar lichtgroen;
   - drill-down gebruikt dezelfde uitgavendetails als de gewone uitgaventegel.

2. **Uitgaven**
   - totale uitgaven over de laatste 4 gekozen perioden;
   - vergelijking met de 4 perioden daarvoor;
   - drill-down naar dag, winkel en kassabon.

3. **Bezochte winkels**
   - aantal unieke bezochte winkels in de laatste 7 dagen;
   - waar zinvol ook aantal winkelbezoeken;
   - drill-down naar winkels en bijbehorende kassabonnen.

4. **Begrote uitgaven**
   - toont steeds 4 dagen, 4 weken of 4 maanden volgens de gekozen schakelaar;
   - verwachte uitgaven blijven gebaseerd op herhalingskoop;
   - grafische verdeling per week;
   - drill-down met basis van de prognose.

## Rolgedrag

- Gebruiker en Beheerder zien hetzelfde dagelijkse dashboard.
- Beheerrechten blijven via **Instellingen** lopen en worden niet als los beheerdashboard op de landingspagina gedupliceerd.
- Frontteamlid ziet hetzelfde huishoud-dashboard als zijn gewone huishoudrol; Frontteam-functionaliteit blijft aanvullend beschikbaar via de bestaande navigatie.
- De bestaande Superuser-omgeving achter **Superuser** blijft de dashboardingang voor functioneel platformbeheer. De IP-eigenaar krijgt geen huishoud-dashboard, Superuseromgeving of technische Platformbeheerfuncties; de eigen landing bevat uitsluitend **Superusers** en **Uitloggen**.
- Platformbeheer wordt niet in het gewone huishoud-dashboard gemengd.

## Platformbeheer en support

- **Platformbeheerder** omvat nu ook de platformbrede supportverantwoordelijkheid.
- De platform-inbox staat onder **Platformbeheer → Meldingen** op `/platform/meldingen`.
- Platformbeheerder heeft daarvoor zowel `platform.support_access.read` als `platform.support_access.mutate`.
- De oude route `/superuser/meldingen` blijft uitsluitend als compatibiliteitsredirect bestaan en verwijst naar Platformbeheer.
- Frontteamleden sturen hun meldingen gebruikerszichtbaar naar **Platformbeheer**; de bestaande support-API en audittrail blijven de autorisatiegrens.
- Superuser kan de platform-inbox gebruiken via de bestaande supportpermissies. De IP-eigenaar heeft geen supportpermissies.

## Navigatie

- De huidige grote hoofdactiekaarten op de mobiele landingspagina verdwijnen zodra hun functionaliteit via dashboardstatus/drill-down en de centrale onderste actiebalk bereikbaar is.
- De onderste mobiele actiebalk blijft maximaal vier recente beschikbare acties plus **Meer** tonen volgens de bestaande app-brede navigatiebaseline.
- Dashboardtegels zijn informatie-eerst en volledig aanklikbaar voor drill-down.
- De vier dashboardtegels kunnen door de gebruiker met muis of touch worden versleept; tijdens het slepen verandert de volgorde direct.
- De gekozen tegelvolgorde wordt per gebruiker lokaal bewaard en bij terugkeer/opstart opnieuw toegepast.

## Datadefinities

- Dashboardcijfers zijn per actief huishouden geïsoleerd.
- Verwijderde, dubbele of niet-afgeronde test-/conceptbonnen tellen niet mee als gerealiseerde aankoop.
- Gekochte artikelen en uitgaven worden gebaseerd op afgeronde/erkende kassabongegevens.
- Bezochte winkels tellen unieke winkels binnen de gekozen periode; meerdere kassabonnen bij dezelfde winkel blijven in drill-down zichtbaar.
- Begrote uitgaven worden expliciet als **verwacht/begroot** gepresenteerd en niet als zeker bedrag.

## Testniveau

TEST_LEVEL_PROVISIONAL: L

Reden: centrale landingspagina, dashboardaggregaties, drill-downroutes en gebruikerszichtbare rolprojectie raken app-brede kernnavigatie en huishouddata. Finale kandidaat vereist de toepasselijke exact-candidate regressie.


## Voormalige losse beheerroute onder Platformbeheer
- De voormalige losse beheer-/testdatapagina is vervallen.
- De oude route `/admin` blijft uitsluitend als beveiligde compatibiliteitsredirect naar **Platformbeheer → Testfixtures**.
- Testfixturebeheer staat onder **Platformbeheer → Testfixtures**.
- Permanente verwijdering van gearchiveerde kassabonnen staat onder **Platformbeheer → Herstel**.
- Kassa releasecontrole en volledige Kassa-inleesregressie worden gestart onder **Platformbeheer → Achtergrondtaken**; status is zichtbaar onder **Platformbeheer → Diagnostiek**.
- De Kassa-startendpoints vereisen `platform.background_jobs.manage`; statuslezing vereist `platform.diagnostics.view`.
- Een huishoudelijke Beheerder krijgt door de huishoudrol geen toegang tot deze technische Platformbeheerfuncties.


## Gebruikerszichtbare rolnamen
- Reguliere huishoudrollen worden uitsluitend getoond als **Gebruiker** en **Beheerder**.
- Legacy keys zoals `household.viewer`, `household.advanced_member` en `household.owner` blijven alleen voor compatibiliteit bestaan en worden niet als aparte gebruikersrollen gepresenteerd.
- De losse gebruikerszichtbare beheeringang bestaat niet meer; huishoudbeheer loopt via **Instellingen**.
- Platformrollen blijven expliciet onderscheiden als **Superuser**, **Platformbeheerder** en **IP-eigenaar**.
- Alleen de **IP-eigenaar** kan Superusers aanstellen of intrekken. Platformbeheerder- en Frontteambeheer vallen niet onder de IP-eigenaarsrol.


## IP-eigenaar vereenvoudigd — PO-besluit 3 oktober 2026
- De IP-eigenaar is geen operationele huishoudrol en heeft geen toegang tot Dashboard, Voorraad, Kassa, Boodschappen, Catalogus, Meldingen, huishoudinstellingen of systeemhuishouden 0.
- De IP-eigenaar erft geen Superuser- of Platformbeheerderrechten.
- Na inloggen krijgt de IP-eigenaar een eigen eenvoudige landing met uitsluitend **Superusers** en **Uitloggen**.
- De beheerpagina **Superusers** toont alleen actieve Superusers. Een nieuwe Superuser wordt privacy-minimaal aangesteld door het e-mailadres van een bestaande Inhuis-gebruiker in te voeren; de IP-eigenaar krijgt geen algemene gebruikersinventaris.
- De backend blijft de autorisatiegrens; directe pogingen om via de IP-eigenaarsbevoegdheid Platformbeheerder te muteren worden geweigerd.
