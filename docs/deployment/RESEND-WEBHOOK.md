# Resend-webhookconfiguratie

## Doel

Rezzerv accepteert inkomende kassabon-e-mails via:

```text
POST /api/receipts/inbound
```

Deze route verwerkt uitsluitend webhooks waarvan de Resend/Svix-handtekening geldig is. De backend controleert de ongewijzigde request body met de headers `svix-id`, `svix-timestamp` en `svix-signature`.

## Verplichte omgevingsvariabele

Voor automatische ontvangst moet de backendcontainer deze variabele krijgen:

```text
REZZERV_RESEND_WEBHOOK_SECRET=<signing secret van de betreffende Resend-webhook>
```

Gebruik uitsluitend de signing secret van precies de webhook die naar `/api/receipts/inbound` verzendt. De waarde wordt in Resend bij de webhookdetails beheerd.

## Veilig beheer

- Sla de echte secret nooit op in Git, Docker Compose, documentatie, logs of screenshots.
- Beheer de waarde in de lokale `.env`, de deployment-secretstore of het hostingplatform.
- Deel de waarde niet met frontendcode; alleen de backendcontainer heeft deze nodig.
- Bij rotatie moet zowel Resend als de deploymentconfiguratie worden bijgewerkt.
- Controleer na rotatie met een echte testlevering dat de webhook HTTP 2xx teruggeeft.

Docker Compose geeft de variabele uitsluitend door vanuit de hostomgeving:

```yaml
REZZERV_RESEND_WEBHOOK_SECRET: ${REZZERV_RESEND_WEBHOOK_SECRET:-}
```

Een lege of ontbrekende waarde wordt niet vervangen door een ingebouwde secret. De inboundroute faalt dan bewust gesloten met HTTP 503 en maakt geen receiptbron of kassabon aan.

## Lokale ontwikkeling

Automatische Resend-inbound kan lokaal uitgeschakeld blijven. In dat geval mag de variabele leeg zijn; handmatige upload en de overige Kassa-functies blijven beschikbaar.

Voor een lokale end-to-endtest wordt de secret alleen in de lokale, niet-gecommitte `.env` geplaatst:

```text
REZZERV_RESEND_WEBHOOK_SECRET=whsec_...
```

De voorbeeldwaarde hierboven is uitsluitend formaatillustratie en geen werkende secret.

## Releasecontrole

Voor een omgeving waarin automatische e-mailontvangst actief moet zijn, controleert de releasecoördinator vóór vrijgave:

1. de Resend-webhook wijst naar de juiste publieke `/api/receipts/inbound`-URL;
2. `REZZERV_RESEND_WEBHOOK_SECRET` is in de deployment-secretstore gevuld;
3. de backendcontainer ontvangt de variabele;
4. een geldige testlevering wordt eenmaal verwerkt;
5. herlevering met dezelfde `svix-id` veroorzaakt geen tweede import;
6. ongeldige of ontbrekende handtekeningen worden vóór receiptverwerking geblokkeerd.
