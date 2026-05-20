# R7c-18a — Rotation-Only Regression Benchmark

## Doel

R7c-18a valideert diagnostic-only of:

```text
rotation-only preprocessing
```

veilig toepasbaar is op de volledige kassabontestset.

Belangrijk:

Er wordt:

- geen productieparser aangepast;
- geen frontend aangepast;
- geen retailerregels aangepast;
- geen statuslogica aangepast.

## Aanleiding

R7c-17 liet zien:

```text
rotate_only > original
```

voor AH foto 3.

Maar:

- regressies op andere bonnen waren nog onbekend;
- production-safe integratie kon daarom nog niet verantwoord plaatsvinden.

## Benchmarkstrategie

Elke bon uit:

```text
supermarkten.zip
```

wordt via twee routes verwerkt:

1. original
2. rotate_only

## Metingen

### OCR metrics

- OCR-regelcount
- price-anchor count
- article-like line count
- footer/payment line count

### Parsing metrics

- winkelherkenning
- datumkandidaten
- totaalbedragkandidaten

### Quality metrics

- parseability score
- payment dominance
- article density

## Regressiedetectie

Een regressie wordt gemarkeerd wanneer:

- OCR-output sterk instort;
- winkelherkenning verloren gaat;
- totaalherkenning instabiel wordt;
- article reconstruction significant verslechtert.

## Belangrijk architectuurprincipe

De benchmark kiest:

```text
nog GEEN productieroute
```

maar:

```text
meet eerst objectief de veiligheid
```

van rotation-only preprocessing.

## Mogelijke vervolgstappen

### Bij succesvolle benchmark

R7c-18b — Integrate Rotation-Only Preprocessing into Production OCR Pipeline

### Bij regressies

R7c-18c — Selective Rotation Routing

waarbij alleen specifieke bonprofielen rotation-only preprocessing krijgen.
