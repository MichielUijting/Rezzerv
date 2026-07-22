# Volledige broninhoud — Rezzerv Release Gate v1.1

Bronbestand: `Rezzerv-Release-Gate_v1.1.md`

# Rezzerv Release Gate v1.10

Status: Verplicht procesonderdeel voor alle toekomstige releases

------------------------------------------------------------------------

## 1. Doel van de Release Gate

De Release Gate zorgt ervoor dat een release pas geleverd kan worden wanneer:
1. De scope correct is afgebakend
2. De wijziging inhoudelijk klopt en geen regressie veroorzaakt
3. De zip correct verpakt en genummerd is
4. De zip zelfstandig kan werken en dus niet als patch wordt aangeboden

Principe:
Eerst betrouwbaar, dan pas verder.

------------------------------------------------------------------------

## 2. Overzicht van de 3 Gates

- Scope Gate
- QA/QC Gate
- Packaging Gate

Alle drie moeten groen zijn vóór levering aan de PO.

------------------------------------------------------------------------

## 3. Gate 1 — Scope Gate

(ONGEWIJZIGD)

------------------------------------------------------------------------

## 4. Gate 2 — QA/QC Gate

Controlepunten:

1. Basisversie klopt  
2. Versienummer incrementeel  
3. Bedoelde wijziging is zichtbaar  
4. Kernfunctionaliteit werkt nog  
5. Geen zichtbare regressie  
6. Instellingen/persistentie werkt  
7. Regressierisico benoemd  
8. PO-teststappen duidelijk  
9. Claims zijn onderbouwd  
10. Werkvolgorde correct  
11. Database-consistentie gecontroleerd  

### Database-consistentie

Verplicht:

- Exacte runtime database is vastgesteld  
- Database komt overeen met backend  
- Database komt overeen met UI  
- Geen gebruik van tijdelijke databases  
- Geen gebruik van alternatieve sqlite-bestanden  
- Docker mount is correct en reproduceerbaar  

### Stopregel

Eén rood punt = release geblokkeerd.

Aanvullend:

Indien onduidelijk is welke database gebruikt wordt:
→ Release direct blokkeren

------------------------------------------------------------------------

## 5. Gate 3 — Packaging Gate

Extra verplicht:

- Database-locatie is consistent met runtime  
- Database-locatie is niet afhankelijk van tijdelijke paden  
- Geen verborgen afhankelijkheden van lokale of tijdelijke databases  

------------------------------------------------------------------------

## 6. Verplicht Release Compliance Blok

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

------------------------------------------------------------------------

## 7. Werkvolgorde

(ONGEWIJZIGD)

------------------------------------------------------------------------

## 8. Nieuwe Harde Stopregels

Aanvulling:

Een release mag niet geleverd worden als:
- databasebron onduidelijk is  
- runtime afhankelijk is van een tijdelijke database  

------------------------------------------------------------------------

## 9. Minimale oplevering

(ONGEWIJZIGD)

------------------------------------------------------------------------

## 10. Samenvatting

Geen Release Zonder 3x Groen
