# Rezzerv Release Gate v1.10
Status: Verplicht procesonderdeel voor alle toekomstige releases

Dit document vult het Release Protocol en het QA/QC-handvest aan en maakt de kwaliteitscontrole blokkerend in plaats van adviserend.
Doel: voorkomen dat een technisch, procedureel of verpakkingsfout ooit nog bij de PO terechtkomt.

Dit document hoort bij:
- Release Protocol
- QA/QC-handvest
- Release-structuur en versienummerbeleid
- Packagingrichtlijnen

## 1. Doel van de Release Gate
De Release Gate zorgt ervoor dat een release pas geleverd kan worden wanneer:
1. De scope correct is afgebakend
2. De wijziging inhoudelijk klopt en geen regressie veroorzaakt
3. De zip correct verpakt en genummerd is
4. De zip zelfstandig kan werken en dus niet als patch wordt aangeboden

Een release zonder volledige Release Gate is ongeldig, ook als de functionaliteit werkt.

Principe:
Eerst betrouwbaar, dan pas verder.

## 2. Overzicht van de 3 Gates
Elke release moet door drie verplichte gates:

- Scope Gate — Afbakening en versies
- QA/QC Gate — Inhoudelijke kwaliteit en regressie
- Packaging Gate — Naamgeving, versie, zip-inhoud

Alle drie moeten groen zijn vóór levering aan de PO.

## 3. Gate 1 — Scope Gate
Wordt uitgevoerd vóór bouwen.

Verplicht vast te leggen:
- Basisversie
- Nieuw versienummer
- Releasecategorie
- Exact wijzigingsdoel
- Wat expliciet niet wordt gewijzigd
- Impact op bestaande functionaliteit
- Regressietest-scope

Releasecategorie (exact één kiezen):
- UI-release
- Backend-release
- Infra-release
- Styleguide-release
- Patch (bugfix)

Stopregels Scope Gate:
Release stopt direct indien:
- basisversie ontbreekt
- versienummer niet verhoogd wordt
- meerdere doelen in één release zitten
- releasecategorie niet is benoemd
- versienummering niet overal in de versie consequent en consistent is doorgevoerd in alle onderdelen
- impact op bestaande functionaliteit niet is benoemd

## 4. Gate 2 — QA/QC Gate
Wordt uitgevoerd na bouwen en testen, vóór packaging.

Verplicht te controleren:
1. Basisversie klopt
2. Versienummer incrementeel
3. Bedoelde wijziging is zichtbaar
4. Kernfunctionaliteit werkt nog
5. Geen zichtbare regressie
6. Instellingen/persistentie werkt (indien geraakt)
7. Regressierisico benoemd
8. PO-teststappen duidelijk
9. Claims zijn onderbouwd
10. Release volgt werkvolgorde Architect → Engineer → QA/QC → Release → PO
11. Database-consistentie gecontroleerd

Database-consistentie betekent:
- Exacte runtime database is vastgesteld
- Database komt overeen met de geteste backend
- Database komt overeen met de getoonde UI
- Geen gebruik van tijdelijke databases
- Geen gebruik van alternatieve sqlite-bestanden
- Docker mount is correct en reproduceerbaar

Stopregel QA/QC Gate:
Eén rood punt = release geblokkeerd.
Geen uitzonderingen.

Aanvullende stopregel:
Indien onduidelijk is welke database gebruikt wordt of meerdere databases mogelijk actief zijn:
❗ Release direct blokkeren

## 5. Gate 3 — Packaging Gate
Wordt uitgevoerd vlak vóór het genereren van de zip.

Verplicht te controleren:
- Zipnaam exact volgens standaard
- Geen suffixes
- Versienummer in zipnaam correct
- VERSION.txt correct
- frontend/public/version.json correct
- Frontend versie-label zichtbaar
- Gewijzigde bestanden zitten in zip
- Zipstructuur logisch
- Packaging geloofwaardig qua omvang
- Database-locatie is consistent met runtime
- Database-locatie is niet afhankelijk van tijdelijke paden
- Geen verborgen afhankelijkheden van lokale of tijdelijke databases

Naamgevingsregel (hard)
Zipnaam altijd exact:
Rezzerv-MVP-vXX.XX.zip

Niet toegestaan:
- -ui-fix
- -patch
- -final
- -new
- -test
- -hotfix

Elke wijziging = nieuw versienummer.

Stopregel Packaging Gate:
Bij fout in naamgeving, versiesync of zipinhoud:
Release blokkeren.

## 6. Verplicht Release Compliance Blok
Elke release moet starten met dit blok:

Release Gate v1.10 – Compliance Check

Basisversie:
Nieuwe versie:
Releasecategorie:
Wijzigingsdoel:
Niet gewijzigd:
Getest:
Niet getest:
Risiconiveau:
Database locatie:
Database validatie:
Scope Gate:
QA/QC Gate:
Packaging Gate:

Pas als alle drie Gates = GROEN:
- Validatierapport tonen
- PO-testinstructie tonen
- Downloadlink geven

## 7. Werkvolgorde in het team
De vaste volgorde is:
1. Architect — scope bepalen
2. Engineer — bouwen
3. Engineer — lokale validatie
4. QA/QC — inhoudelijke controle
5. Release Coordinator — packaging en versies
6. PO — functionele test

Engineers leveren nooit rechtstreeks aan de PO.

## 8. Nieuwe Harde Stopregels
Per direct gelden deze stopregels:

Een release mag niet geleverd worden als:
- basisversie ontbreekt
- versienummer niet verhoogd is
- zipnaam suffix bevat
- VERSION.txt niet klopt
- version.json niet klopt
- packaging niet gecontroleerd is
- regressierisico niet benoemd is
- meerdere wijzigingen in één release zitten
- databasebron onduidelijk is
- runtime afhankelijk is van een tijdelijke database

## 9. Minimale oplevering per release
Vanaf nu bevat elke oplevering exact:
1. Release Gate Compliance Check
2. Validatierapport
3. PO-testinstructie
4. Download zip

Niet meer:
- losse logbestanden
- losse technische uitleg
- ongestructureerde changelogs

## 10. Samenvatting – Belangrijkste regel van het project
De belangrijkste procesregel van Rezzerv wordt hiermee:

Geen zip zonder:
- Scope Gate groen
- QA/QC Gate groen
- Packaging Gate groen

Korter geformuleerd:
“Geen Release Zonder 3x Groen”

Dit is de structurele borging die voorkomt dat dezelfde fouten opnieuw gebeuren.
