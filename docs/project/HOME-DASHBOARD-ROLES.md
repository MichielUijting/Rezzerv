# Inhuis dashboard en rollen — implementatiescope

Status: taakscope voor de nieuwe landingspagina en vereenvoudigde gebruikersrollen.

## Rollen

Gebruikerszichtbaar gelden voor deze taak:
- **Gebruiker** — reguliere huishoudgebruiker;
- **Beheerder** — beheer van het eigen huishouden;
- **Frontteamlid** — aanvullende platformrol bovenop Gebruiker of Beheerder;
- **Platformbeheerder** — support en technisch platformbeheer;
- **Superuser** — inclusief de hoogste IP-eigenaarfuncties voor deze productfase.

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
- Beheerrechten blijven via **Instellingen** lopen en worden niet als los Admin-dashboard op de landingspagina gedupliceerd.
- Frontteamlid ziet hetzelfde huishoud-dashboard als zijn gewone huishoudrol; Frontteam-functionaliteit blijft aanvullend beschikbaar via de bestaande navigatie.
- De bestaande Superuser-omgeving achter **Superuser** blijft inhoudelijk intact en is de dashboardingang voor Superuser/IP-eigenaar.
- Platformbeheer wordt niet in het gewone huishoud-dashboard gemengd.

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
