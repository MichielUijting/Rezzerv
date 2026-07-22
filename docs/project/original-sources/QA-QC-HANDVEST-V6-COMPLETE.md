# Volledige broninhoud — Rezzerv QA/QC-handvest v6

Bronbestand: `Rezzerv-QA-QC-handvest v6.docx`

*Doel: kwaliteitsverlies voorkomen, regressies vroeg stoppen en alleen
gecontroleerde releases naar de PO laten gaan.*

| **Status van QA/QC** | Poortrol tussen engineer en PO             |
|----------------------|--------------------------------------------|
| **Kernbeslissing**   | Geen QA/QC-groen = geen release naar de PO |

# 1. Rol en mandaat

- QA/QC is de kwaliteitswachter tussen engineer en PO.

- De rol heeft vetorecht: geen QA/QC-groen betekent geen release naar de
  PO. Twijfel over basis, packaging of regressie blokkeert de release
  automatisch.

- Nieuwe functionaliteit weegt nooit zwaarder dan gebroken bestaande
  functionaliteit.

# 2. Kerndoel

QA/QC borgt dat een release op de juiste basis is gebouwd, volledig en
geloofwaardig is verpakt, het bedoelde wijzigingsdoel echt bevat, geen
zichtbare regressie veroorzaakt en toetsbaar is voor de PO in gewone
gebruikerstermen.

# 3. Centrale regels

1.  **Regel 1 — Eén betrouwbare basis**

> Elke release vermeldt expliciet op welke vorige versie zij bouwt,
> waarom die basis betrouwbaar is en dat niet ongemerkt is teruggevallen
> naar een oudere of verkeerde codebasis.

2.  **Regel 2 — Eén hoofddoel per release**

> Elke release heeft exact één hoofddoel. Gemengde releases zijn niet
> toegestaan.

3.  **Regel 3 — Geen claim zonder bewijs**

> Woorden als uitgevoerd, gereed, opgelost of gefixt mogen pas worden
> gebruikt als aantoonbaar is welke basisversie is gebruikt, welke
> bestanden zijn aangepast, welke acceptatiecheck is geslaagd en welke
> risico’s nog openstaan. Een eis is dat een claim altijd gebaseerd is
> op onderzoek van de voorgaande versie (zip).

4.  **Regel 4 — Regressie wint altijd**

> Als een nieuwe versie bestaande werkende functionaliteit aantast, is
> de release afgekeurd, ook als de nieuwe wijziging deels werkt. Dus ook
> geen zip meer naar de PO zolang laag 1, laag 2 en laag 3 niet minimaal
> akkoord zijn voor de scope die door de release geraakt wordt.

5.  **Regel 5 — Instellingenfundament eerst**

> Als instellingen niet betrouwbaar zichtbaar zijn, opslaan of
> terugkomen na refresh of opnieuw openen, dan zijn functionele
> vervolgtests ongeldig.

6.  **Regel 6 — Productbesluit is leidend**

> Als de PO een functionele keuze heeft vastgelegd, mag een volgende
> release daar niet stilzwijgend van afwijken.

7.  **Regel 7 — Diagnose mag niets verdringen**

> Diagnose, debug of logging mag alleen toegevoegd worden bovenop
> bestaande werkende functionaliteit, nooit ten koste daarvan.

8.  **Regel 8 — Packaging is onderdeel van kwaliteit**

> Een zip is pas acceptabel als de inhoud volledig is, de structuur
> logisch is en de omvang geloofwaardig is ten opzichte van eerdere
> volledige releases. De package moet compleet en zelfstandig zijn, dus
> niet alleen de wijzigingen ten opzichte van een vorige versie. En al
> zeker geen patches. Een versie heeft altijd de naam Rezzerv-v99.99.99
> waarbij 9 staat voor een cijfer en elke versie wordt met 1 opgehoogd.
> Per versie wordt een complete zip aangeboden en die bevat geen
> toelichting op de versie. Die toelichting moet aangeboden worden in de
> chat en niet de zip zelf.

9.  **Regel 9 — De PO is geen technische kwaliteitscontroleur**

> De PO toetst functioneel gedrag en hoort geen packagingfouten,
> verkeerde basisversies of regressies vooraf te moeten ontdekken.

10. **Regel 10 — Bij herhaalde misser: stop en reset**

> Bij twee misleidende of regressieve opleveringen op rij geldt: geen
> doorpatchen, eerst terug naar de laatste betrouwbare basis en de
> oorzaak vaststellen.

# 4. Verplichte QA/QC-poort vóór elke release

| **\#** | **Controlepunt**                                                                                     |
|--------|------------------------------------------------------------------------------------------------------|
| 1      | Basisversie klopt                                                                                    |
| 2      | Versienummering klopt incrementeel                                                                   |
| 3      | Zip is volledig en geloofwaardig verpakt                                                             |
| 4      | Het bedoelde wijzigingsdoel is zichtbaar aanwezig                                                    |
| 5      | Bestaande kernfunctionaliteit is niet stukgegaan                                                     |
| 6      | Instellingen en persistentie werken, als die geraakt zijn                                            |
| 7      | Regressierisico is benoemd                                                                           |
| 8      | PO-teststappen zijn helder en niet-technisch                                                         |
| 9      | Een frontendrelease is automatisch NO-GO als de geraakte route niet echt is geopend vóór oplevering. |

Eén rood punt betekent: release blokkeren.

# 5. Verplichte opleverinformatie per release

Elke release bevat minimaal: basisversie, nieuw versienummer, exact
wijzigingsdoel, lijst van aangepaste onderdelen, wat expliciet niet is
gewijzigd, bekende risico’s en eenvoudige PO-teststappen.

# 6. Stopcriteria

QA/QC blokkeert een release direct bij: verkeerde basis, onvolledige
zip, opvallend afwijkende packaging zonder verklaring, regressie in het
instellingenfundament, mismatch met productbesluit van de PO, diagnose
die werkende UI verdringt of claims zonder bewijs.

# 7. Werkvolgorde in het team

- De vaste volgorde is: Architect bepaalt richting en afbakening,
  Engineer bouwt de afgesproken wijziging, QA/QC controleert basis,
  regressie, packaging en toetsbaarheid, en de PO test pas daarna
  functioneel.

- Geen engineer rechtstreeks naar de PO zonder QA/QC-poort.

# 8. Praktische QA/QC-checklist voor Rezzerv

- Is dit gebouwd op de afgesproken vorige versie?

- Is de zip qua omvang en inhoud geloofwaardig?

- Is de bedoelde wijziging echt zichtbaar?

- Is oude werkende functionaliteit nog aanwezig?

- Zijn instellingen nog correct zichtbaar, opslaanbaar en persistent?

- Is er geen terugval naar oudere UI of oude logica?

- Zijn de PO-teststappen begrijpelijk zonder technische kennis?

# 9. Toepassing vanaf nu

Vanaf nu geldt voor Rezzerv: geen nieuwe zip zonder QA/QC-poort, geen
'gereed' zonder aantoonbare basiscontrole, geen verder functioneel
testen als het instellingenfundament niet stabiel is, en liever één
terechte afkeuring dan meerdere misleidende opleveringen.

# 10. Beslisregel

Eerst betrouwbaar, dan pas verder.

| **Beslisregel: Eerst betrouwbaar, dan pas verder.** |
|-----------------------------------------------------|
