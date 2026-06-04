# Kassa releasecontrole

## Doel

Deze controle borgt dat het Kassa-inleesproces minimaal werkt voor de vijf ondersteunde supermarktketens voordat een release door mag.

## Minimale controleset

De minimale releasecontrole gebruikt exact 1 kassabon per winkelketen:

| Winkelketen | Case ID | Bestand |
|---|---|---|
| Albert Heijn | `ah_app_1` | `ah_app_1.pdf` |
| ALDI | `aldi_foto_1` | `aldi_foto_1.jpg` |
| Jumbo | `jumbo_app_1` | `jumbo_app_1.png` |
| PLUS | `plus_foto_1` | `plus_foto_1.jpg` |
| Lidl | `lidl_app_1` | `lidl_app_1.png` |

De set is vastgelegd in:

```text
backend/app/testing/kassa_regression/smoke_manifest.json
```

## Acceptatiecriterium

Een release mag alleen door als de Kassa-releasecontrole het volgende resultaat geeft:

```text
5 getest
5 geslaagd
0 gefaald
0 geblokkeerd
```

## Datum en tijd

Datum/tijd vormt nooit een validatiecriterium voor de Kassa-inleesregressie of Kassa-releasecontrole.

Datum/tijd mag wel diagnostisch in rapportage zichtbaar zijn, maar mag nooit een test laten falen.

## Relatie tot volledige regressie

Naast deze minimale releasecontrole bestaat de volledige Kassa-inleesregressie met 14 kassabonnen. Die volledige regressie is bedoeld voor parserontwikkeling en bredere dekking.

De release-gate gebruikt bewust niet alle 14 bonnen, maar exact 1 representatieve bon per winkelketen.

## Testbron en isolatie

De controle mag niet afhankelijk zijn van de normale applicatiedatabase als acceptatiebron. De bonnen moeten opnieuw door het inleesproces worden verwerkt in een geïsoleerde testcontext of tijdelijke testdatabase.
