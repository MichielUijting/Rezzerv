# Deprecated regression runner

Deze browser-regressierunner is deprecated sinds R7c34.

Niet meer gebruiken voor receipt/OCR-validatie.

Nieuwe route:

```text
tools/r7c33_receipt_validation_runner.py
```

Reden:

- oude runner veroorzaakte lifecycleproblemen;
- oude runner veroorzaakte poortconflicten;
- oude runner veroorzaakte fixture-state leakage;
- oude runner had te brede scope voor receipt/OCR-validatie.

Architect-gate:

Nieuwe receipt/OCR-validatie loopt backend-only via R7c33d.
Deze map is alleen historisch archief en mag niet opnieuw als actieve testinfra worden gebruikt.
