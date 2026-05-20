# R7c-18b — Rotation Confidence & Safe Angle Detection

## Doel

R7c-18b bepaalt diagnostic-only wanneer:

```text
rotation-only preprocessing
```

veilig genoeg is om toe te passen.

Belangrijk:

Er wordt:

- geen productieparser aangepast;
- geen frontend aangepast;
- geen retailerregels aangepast;
- geen OCR-engine vervangen.

## Aanleiding

R7c-18a liet zien:

- AH foto 3 verbetert;
- Aldi foto 2 licht verbetert;
- maar Jumbo foto 1 zwaar regressief wordt.

Root cause:

```text
onveilige automatische hoekdetectie
```

waardoor een foutieve hoek van 72 graden werd gekozen.

## Nieuwe architectuurregel

Niet:

```text
altijd roteren
```

maar:

```text
alleen roteren wanneer veilig
```

## Nieuwe signalen

### Angle signals

- Hough line angles
- min-area-rect angle
- consensus tussen lijnen
- plausibility van hoek

### OCR stability signals

- OCR line ratio after rotation
- parseability delta
- winkelstabiliteit
- totaalstabiliteit

## Safe routing regels

Rotation-only wordt alleen toegestaan als:

- abs(angle) <= 45 graden
- confidence >= threshold
- OCR-output niet instort
- winkeldetectie stabiel blijft
- totaaldetectie stabiel blijft

## Fallbackstrategie

Bij twijfel:

```text
fallback naar original
```

Dit maakt de pipeline:

```text
fail-safe
```

in plaats van:

```text
agressief normaliseren
```

## Verwachte vervolgstap

Bij succesvolle benchmark:

R7c-18c — Integrate Safe Rotation Preprocessing

waarbij:

- rotation-only preprocessing optioneel wordt;
- confidence gating actief blijft;
- originele route altijd beschikbaar blijft als fallback.
