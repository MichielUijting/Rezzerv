# PR3 — Geschatte beginvoorraad beoordelen, corrigeren en bevestigen

Status: ontwikkeling op Draft-PR; geen automatische voorraadboeking bij historische bonimport.
TEST_LEVEL_PROVISIONAL: L
Reden: bevestigde voorraadmutaties, household-autorisatie, Alembic-persistentie en gebruikersinterface.

## Functionele afspraak

In Instellingen → Beginvoorraad beoordelen ziet een bevoegde huishoudbeheerder de *onbevestigde* uitkomst van PR2. Deze is geen fysieke voorraad. Het overzicht vermeldt artikelen, aantal aankoopdagen, laatste aankoop, gemiddelde koopinterval, geschatte beginvoorraad, eenheid en bewijsstatus. Een huishouden zonder historische cutover krijgt een uitleg, geen verzonnen resultaten.

Een beheerder kan een voorgesteld aantal *handmatig* corrigeren. Alleen een expliciet geselecteerde, geldige, bevestigde huishoudartikelidentiteit met een eenduidige fysieke tel-eenheid **stuk** kan als beginvoorraad worden geboekt. Bij artikelgroepen met meerdere huishoudartikelen, producten zonder uniek bewezen huishoudartikel en kg/l-schattingen volgt uitsluitend een uitleg; hiervoor is nog aparte identiteit-/eenheidsbeoordeling nodig. Geen naamgebaseerde artikelcreatie of eenheidsconversie.

De bevestigingsdialoog toont artikel, handmatig gekozen aantal en de waarschuwing dat daarmee **werkelijke voorraad** wordt aangemaakt. Annuleren, sluiten, niet kiezen en falen doen niets. Een bevestiging van nul registreert de keuze maar maakt geen voorraadpositie of evenement aan.

## Autoriteit en concurrentiebeveiliging

De server bepaalt huishouden, actor en `household_settings.manage` aan de hand van de canonieke sessie. Geen client-meegestuurd household-ID als autoriteit. Een versie-/bewijsfingerprint bindt elke schrijfactie aan het actuele historische voorstel. Een andere cutover, een nieuwe bon of een gewijzigde match maakt een eerder geopend voorstel ongeldig: opnieuw laden.

Voor de eerste bevestiging controleert de server opnieuw:
- exact één actief huishoudartikel in het geautoriseerde huishouden;
- een voorraadgerechtigde tel-eenheid en een geheel, niet-negatief aantal tot 10.000;
- historische cutover en bronanalyse nog actueel;
- nul bestaande voorraadregels én nul eerdere voorraad-events voor dit artikel;
- geen eerdere beginvoorraadbevestiging voor dit huishoudartikel.

De database bewaart maximaal één bevestiging per huishouden/artikel. De invoeging, eventueel nieuwe *locationless* voorraadpositie en het auditevent gebeuren in één transactie. Geen koopbon, importstatus, Catalogusidentiteit, locatie-instelling of ander huishouden wordt gewijzigd.

Na een succesvolle bevestiging toont de interface de gekozen hoeveelheid, ook wanneer de oorspronkelijke berekende suggestie afweek. Een nieuwe poging mag niets dubbel boeken. Andere voorraadartikelen behouden hun bestaande voorraad- en Bijna-op-gedrag.

## Acceptatie

Bewijs vereist voor unieke identiteiten, pagina's, correctie, nul-keuze, éénmalige bevestiging, herhaald POST, stale-fingerprint, huishouden A/B, viewer/huishoudbeheerder, bestaande voorraad/event, ontbreken cutover, niet-fysieke regels en gemengde eenheden. Test ook geen locatieverplichting en geen indirecte wijziging van Kassa/Uitpakken. Eerst gerichte tests, daarna normale CI/preflight en definitieve patchversie; F7 Full uitsluitend op uiteindelijke kandidaat-SHA. Zonder afzonderlijke PO-GO geen merge/deployment.
