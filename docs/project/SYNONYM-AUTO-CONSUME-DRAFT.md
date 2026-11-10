# Synoniemgestuurde automatische afboeking — onderzoeks- en implementatiegrens

Status: Draft-voorbereiding, **geen wijziging aan actieve voorraadlogica**.

## Objectief vastgesteld op main (10 november 2026)

- `product_day_auto_consume_service.compute_product_day_auto_deduction` groepeert per `household_id + household_article_id + kassabondatum`.
- `main.determine_auto_consume_decision` haalt huishoudmodus en eventuele artikeloverride op en roept die berekening aan.
- `main.create_auto_repurchase_event` en `apply_inventory_consumption` werken met exact één huishoudartikel; het resultaat wordt door `inventory_events` vastgelegd.
- Centrale bevestigde synoniemen staan in `article_synonym_links` als **rechtstreekse** Catalogusparen; A-B plus B-C is géén bewijs voor A-C.
- `household_articles.global_product_id` is de benodigde gecontroleerde koppeling van privéhuishoudartikel aan centraal product. Namen/bontekst mogen dit niet vervangen.

## Dit eerste codeblok

`confirmed_household_synonym_pair` is een **read-only voorwaardecontrole** voor de latere afboeking. Alleen een ondubbelzinnig bevestigd rechtstreeks paar, één actieve huishoudrepresentatie per centraal product, hetzelfde huishouden en actieve producten geven twee huishoudartikel-ID's terug. Bij ontbrekend bewijs, dubbele representaties of ketens blijft uitsluitend het oorspronkelijke ID over.

De functie is bewust nog **niet aan de muterende aankoopketen aangesloten**. Bestaande afboekingen blijven onveranderd totdat de volgende punten als één veilige keten zijn afgedekt.

## Vereist voordat de muterende synoniemafboeking mag worden ingeschakeld

1. Objectief de actuele huishoudinstelling en artikeloverrides van huishouden 1 uitlezen; geen waarde aannemen op basis van historische chatinformatie.
2. Verifiëren welke actieve huishoudartikelen een bewijsbare Cataloguskoppeling én rechtstreeks synoniempaar hebben; ontbrekende identiteiten separaat herstellen, nooit op naam matchen.
3. Dezelfde-dagbescherming uitbreiden van individueel ID naar veilig paar zonder de bestaande kassabon-dagvolgorde te verbreken.
4. Voor beide afboekmodi per voorraadpositie de correcte afboekvolgorde, beschermde nieuwe aankopen en locatieverdeling berekenen.
5. **Elke afboeking vastleggen als een event op het huishoudartikel waarvan de voorraad daadwerkelijk vermindert**, niet blind op het gekochte artikel; hierna ledger en actuele voorraad voor beide huishoudartikelen reconciliëren.
6. Individuele overrides die tegenstrijdig zijn, ambiguïteit, ontbrekende catalogusidentiteit, oudere teruggedateerde aankopen en ongeldige datum fail-closed afhandelen.
7. Gerichte tests: dezelfde dag meerdere winkels, verschillende dagen, verschillende locaties, 0/1/2 modi, household-isolatie, geen nieuwe aankoop afboeken, negatieve/dubbele effecten voorkomen; daarna normale en exact-candidate repo-gates.

De bestaande gegevens van Mijn huishouden1 worden **niet** aangepast door deze PR. Geen merge zonder aparte expliciete PO-GO.
