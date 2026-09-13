# Wijzigingsrisico en testniveaus S/M/L

Status: bindend ontwikkel- en CI-proces voor alle nieuwe wijzigingsverzoeken.

## Doel

Niet iedere wijziging heeft hetzelfde regressierisico. Rezzerv gebruikt daarom drie testniveaus. De classificatie wordt vóór implementatie voorlopig vastgelegd en na implementatie opnieuw, automatisch, bepaald uit de volledige kandidaatdelta. Alleen opschalen is toegestaan; automatisch afschalen is verboden.

De machineleesbare bron is `quality/ci/change_risk_policy.json`. De fail-closed classifier is `scripts/ci/classify_change_risk.py`.

## Verplichte behandeling van ieder wijzigingsverzoek

Voordat code of configuratie wordt gewijzigd, wordt expliciet vastgelegd:

```text
TEST_LEVEL_PROVISIONAL: S|M|L
Reden: <korte risicomotivatie>
```

Deze voorlopige classificatie hoort ook in de PR-body. Ontbreekt de marker, dan classificeert CI fail-closed als voorlopig niveau L.

Na implementatie classificeert CI de volledige `base SHA ... candidate SHA` delta. De definitieve classificatie is altijd het hoogste niveau van:

1. de voorlopige classificatie uit het wijzigingsverzoek;
2. de classificatie van de werkelijke kandidaatdelta.

Voorbeeld: voorlopig S + frontendlogica M = definitief M. Voorlopig L + documentatiedelta S blijft definitief L.

## Niveau S — Small / Fast

Bestemd voor aantoonbaar laag-risico wijzigingen, zoals documentatie en de canonieke version-only bundle waarbij JSON/package-inhoud buiten het `version`-veld ongewijzigd blijft.

Verplicht:

- F7-RISK classificatie;
- F7-02 goedkope authorities;
- gerichte build/smoke wanneer de wijziging dat vereist.

Voor niveau S selecteert F7-02 geen zware shared full-stack clusters. De Full Regression decision blijft zichtbaar, maar dispatcht de elf zware Full Regression authorities niet.

## Niveau M — Normal

Bestemd voor normale applicatie- en testwijzigingen die geen backend-core, schema, runtime-infrastructuur of CI-orchestratie wijzigen. Voorbeelden zijn reguliere frontendlogica en niet-centrale tests.

Verplicht:

- F7-RISK classificatie;
- F7-02 PR Fast Regression met de door de volledige delta geselecteerde shared authorities.

De Full Regression decision blijft zichtbaar, maar de elf zware Full Regression authorities zijn niet verplicht.

## Niveau L — High Risk

Bestemd voor wijzigingen met hoog systeem- of regressierisico. Hieronder vallen minimaal:

- backend runtimecode en `backend/app/**`;
- Alembic/schema- en receipt-ingestioncode;
- Docker/startup/release-infrastructuur;
- CI- en testorchestratie onder `.github/workflows/**`, `quality/ci/**` en `scripts/ci/**`;
- wijziging van deze policy of de ontwikkelregels;
- onbekende paden waarvoor geen expliciete classificatieregel bestaat.

Verplicht:

- F7-RISK classificatie;
- F7-02 PR Fast Regression;
- F7 Full Regression exact-candidate gate met alle geregistreerde zware authorities.

Een handmatige dispatch van de Full Regression gate forceert altijd niveau L.

## Fail-closed regels

- Een ontbrekende voorlopige classificatie wordt L.
- Een onbekend pad wordt L.
- Een wijziging aan de classifier, policy of CI-orchestratie wordt L.
- De werkelijke kandidaatdelta mag de voorlopige classificatie verhogen.
- De werkelijke kandidaatdelta mag de voorlopige classificatie nooit automatisch verlagen.
- Alleen de volledige kandidaatdelta telt; uitsluitend de laatste commit bekijken is ongeldig.
- Testniveau is geen merge-autorisatie. Expliciete PO-GO blijft vereist waar het bestaande proces dat voorschrijft.

## Version-only Fast Path

De version-only Fast Path geldt alleen wanneer alle gewijzigde bestanden binnen de canonieke versie-set vallen en de JSON/package-bestanden buiten het `version`-veld identiek zijn. Zodra in dezelfde kandidaat ook andere code, workflow- of configuratiebestanden worden gewijzigd, vervalt deze uitzondering en bepaalt de normale path-policy het niveau.

## Bewijs en audit

De workflow `Change risk classification` schrijft voor iedere PR machine-readable evidence met:

- base SHA;
- candidate SHA;
- voorlopige classificatie;
- delta-classificatie;
- definitief testniveau;
- lijst gewijzigde bestanden met risicoreden;
- verplichte gates.

F7-02 en F7 Full Regression voeren dezelfde classifier opnieuw uit op hun eigen exacte candidate checkout. Daardoor is classificatie geen vrijblijvende PR-metadata maar onderdeel van de uitvoerbare merge-authority.
