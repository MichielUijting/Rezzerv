# R7c-13 — Semantic line filtering diagnostics

## Doel

Diagnostic-only vaststellen welke gereconstrueerde topology-regels uit `AH foto 3.jpg` plausibele artikelregels zijn en welke regels metadata, betaalterminalinformatie, footer of totaalregels zijn.

## Aanleiding

R7c-12 toonde dat conservative topology reconstruction extra structuur terugvindt:

- `detected_total_amount = 5,40`
- `reconstructed_article_line_count = 3`

Maar de gevonden candidate pairs waren semantisch onjuist, zoals totaal- en terminalregels die als artikelregels werden gezien.

## Scope

Wel:

- alleen AH foto 3;
- diagnostic-only;
- topology-regels classificeren;
- rejection reasons rapporteren.

Niet:

- geen parserwijziging;
- geen SSOT-wijziging;
- geen productiegedrag;
- geen AH-specifieke producthack.

## Line types

De diagnostiek gebruikt minimaal:

```text
PAYMENT_TERMINAL
PAYMENT_CARD
NFC
TOTAL_LINE
DATE_TIME
FOOTER
ARTICLE_CANDIDATE
UNKNOWN
```

## Output per regel

```text
line_text
line_type
contains_price
price_value
is_article_candidate
rejection_reason
```

## Besluitcriterium

Alleen als de semantische filtering plausibele artikelregels onderscheidt van payment/footer/noise, mag een latere stap een gecontroleerde topology fallback voorbereiden.
