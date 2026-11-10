# Synoniemgestuurde automatische voorraadafboeking — PR #670

Status: implementatie op Draft-taakbranch. Geen backfill, wijziging aan huishoudeninstellingen of historische data. Definitieve Ready-/F7-gates blijven verplicht.

## Domeincontract

Automatisch afboeken bij een volgende aankoop blijft gestuurd door de bestaande instelling **per huishouden**, met optionele individuele artikeloverrides:
- `none`: geen automatische afboeking.
- `consume_purchased_quantity`: maximaal het nieuw gekochte aantal van de vooraf bestaande voorraad afboeken.
- `consume_all_existing_before_purchase`: alle bestaande voorraad afboeken vóór de nieuwe aankoop.

De koper behoudt het eigen `household_article_id`. Alleen de verbonden component van **expliciet bevestigde** centrale `article_synonym_links` vormt de groep. Zo vormen de afzonderlijk bevestigde relaties A–B en B–C samen één groep van A, B en C; een losse tekstovereenkomst is nooit voldoende. Alleen eenduidig gekoppelde actieve huishoudartikelen uit **hetzelfde huishouden** doen mee. Een ontbrekende huishoudrepresentatie van een centraal groepsproduct is toegestaan, maar draagt geen voorraad bij. Meerdere actieve huishoudartikelen bij één centraal product, inactieve groepsproducten of uitzonderlijk grote groepen (meer dan 200 Catalogusproducten) blokkeren de groepsafboeking. Er vindt geen naamherkenning, automatische huishoudsamenvoeging of wijziging aan de bevestigde Catalogusparen plaats. Ontbrekende of dubbele koppelingen, vertakkingen, tegenstrijdige effectieve afboekmodi en artikelafhandeling `DIRECT_CONSUMPTION` vallen terug op de bestaande individuele logica.

## Bestaande twee verwerkingsroutes

De standaard kassabonbatch en de bestaande locatievrije verwerking via `purchase_import_location_policy_patch` gebruiken allebei `plan_confirmed_synonym_deduction` en `apply_confirmed_synonym_deduction`. Voor de locatievrije route wordt de kassabondatum nu ook aan de bestaande individuele productdagberekening meegegeven.

De synoniemgroep gebruikt de **kassabondatum** als kalenderdag en telt eerdere aankopen en automatische afboekingen van **alle leden** samen. Het verschil tussen de cumulatieve gewenste en reeds uitgevoerde afboeking is de enige nieuwe afboeking. Aankopen van dezelfde dag, óók uit een andere winkel of onder het andere synoniem, worden per opgeslagen voorraadlocatie beschermd. Een onvoldoende verklaarbare locatie, verouderde kassabondatum of ontbrekend bewijs schakelt groepsverwerking veilig uit.

De groep verdeelt afboeking over uitsluitend vóór de aankoop bestaande, actieve **voorraadregels**. Per afgeschreven regel ontstaan een `auto_repurchase`-event op het werkelijk afgeboekte `household_article_id` met de daadwerkelijke locatie en een conditionele aanpassing of verwijdering van exact die voorraadregel. De aankoop blijft een apart event op het aangeschafte artikel. De huidige product-/huishoudartikelidentiteiten, historie, barcodes en instellingen blijven ongewijzigd.

Om het gedrag van de bestaande per-regel foutafhandeling te beveiligen, gebruiken groepsaankopen een geneste transactiesavepoint rond aankoop **én** groepsafboeking. Bij enige fout wordt dit geheel teruggedraaid vóór de bestaande foutstatusregistratie; er mag geen half verwerkt groepsverbruik achterblijven.

## Reikwijdte, migratie en beperkingen

Deze wijziging bevat geen eenmalige terugwerkende correctie van historische voorraad en geen synoniemgroepsvorming bij onbevestigde productidentiteit. Die vervolgstappen horen bij het afzonderlijke Cataloguskoppelingstraject. De actuele afboekinstelling voor een huishouden wordt niet aangepast.

Synoniemen werken alleen waar een bevestigde Catalogus-verbindingsgroep en eenduidige huishoudartikelidentiteiten zijn aangetoond. Bij ambiguïteit of niet-ondersteunde teruggedateerde verwerking blijft de reeds bestaande individuele afboeklogica van kracht. Bestaande private huishoudgegevens worden niet naar deze publieke repository geschreven.

## Kwaliteit en bewijs

- `backend/tests/test_synonym_auto_consume_identity.py`: bevestigde A–B–C-ketens, vertakkingen en cycli, identiteitsbewijs, duplicaten, inactieve leden en huishoudisolatie.
- `backend/tests/test_synonym_auto_consume_service.py`: beide afboekmodi, groepen met drie of meer leden, uitgeschakeld, zelfde dag verschillende winkels, locatiebehoud, bescherming nieuwe voorraad, conflicterende overrides en falende mutaties.
- `backend/tests/test_synonym_auto_consume_route_wiring.py`: zowel reguliere als locatievrije kassabonbatch gebruikt dezelfde planner/schrijver en aankoopdatum.
- `backend/tests/postgresql_synonym_auto_consume_selftest.py`: echte PostgreSQL 17-test met uitsluitend tijdelijke tabellen, bevestigde A–B–C-groep (zonder directe A–C-link), automatische mutaties op de juiste artikel- en locatie-ID's, beide afboekmodi en household-isolatie.
- De bestaande `temporal-inventory-validation` en nieuwe `synonym-auto-consume-postgresql-validation` workflows voeren de gerichte tests uit.

Groene gerichte tests zijn geen toestemming tot Ready, merge of productie. Die stappen houden de bestaande branch-, versie- en exact-candidate-gates en expliciete PO-GO.
