# R7c-3 — canonical supermarket fixture registry

Status: deterministic supermarket regression governance  
Branch: `sync/local-rezzerv-receipt-basis-v2`

## Doel

R7c-3 introduceert stabiele canonical fixture identifiers voor supermarktregressies.

R7c-2 heeft bewezen dat:

- alle 14 supermarktfixtures correct gekoppeld kunnen worden aan baseline V6;
- geen baseline-match ontbreekt;
- de supermarkt-scope expliciet afgebakend is.

R7c-3 bouwt daarop verder door deterministische fixture-identiteiten toe te voegen.

## Waarom canonical fixture IDs nodig zijn

Bestandsnamen alleen zijn onvoldoende stabiel voor regressie-infrastructuur.

Problemen:

- `.jpg` versus `.jpeg`;
- case-verschillen;
- toekomstige hernoemingen;
- verschillende bronvormen (app/foto/pdf);
- mogelijke fixtureduplicaten.

Daarom introduceert R7c-3:

```text
canonical_fixture_id
```

Deze ID blijft stabiel zolang:

- de baseline receipt hetzelfde blijft;
- het fixturetype hetzelfde blijft.

## Scope

Alleen supermarktfixtures.

Niet in scope:

- Gamma;
- Hornbach;
- Action;
- Bol;
- Coolblue;
- Karwei;
- MediaMarkt.

## Canonical ID-opbouw

Formaat:

```text
sm_<receipt_id>_<store>_<source_kind>_<fixture_slug>
```

Voorbeelden:

```text
sm_r002_ah_app_ah_app_1
sm_r003_ah_foto_ah_foto_1
sm_r016_jumbo_app_jumbo_app_1
sm_r018_lidl_app_lidl_app_1
sm_r014_plus_foto_plus_foto_1
```

## Canonical componenten

### receipt_id

Bron:

```text
baseline_receipt_id
```

Reden:

De baseline blijft de functionele source of truth.

### store

Gestandaardiseerde store slug:

| Store | Slug |
|---|---|
| Albert Heijn | ah |
| Aldi | aldi |
| Jumbo | jumbo |
| Lidl | lidl |
| Plus | plus |

### source_kind

Afgeleid uit fixture filename:

| Bron | source_kind |
|---|---|
| App export | `app` |
| Foto | `foto` |
| Scan/PDF | `scan` |

## Tooling

Toegevoegd:

```text
tools/check_r7c3_supermarket_canonical_registry.py
```

Eigenschappen:

- standalone;
- geen backend imports;
- geen SQLAlchemy;
- geen OCR-runtime;
- deterministic output.

## Invoer

Input:

```text
r7c2_supermarket_registry.csv
```

Dus:

- R7c-3 bouwt bovenop R7c-2;
- fixture inventory blijft de eerste waarheid;
- canonical IDs worden daarvan afgeleid.

## Tool-validaties

De tool valideert:

- exact 14 supermarktfixtures;
- alle fixtures matched;
- alle fixtures target `Gecontroleerd`;
- alle fixtures in supermarket-scope;
- unieke canonical IDs;
- vaste store mappings aanwezig.

## Voorbeeldgebruik

```powershell
python tools/check_r7c3_supermarket_canonical_registry.py `
  --registry ".\tmp\r7c2_supermarket_registry.csv"
```

Optioneel:

```powershell
python tools/check_r7c3_supermarket_canonical_registry.py `
  --registry ".\tmp\r7c2_supermarket_registry.csv" `
  --csv-out ".\tmp\r7c3_canonical_registry.csv"
```

## Resultaat van R7c-3

Na R7c-3 bestaan:

- een expliciete supermarktfixture-regressiescope;
- deterministische fixture-identiteiten;
- reproduceerbare fixtureverwijzingen;
- een stabiele basis voor regression runners.

## Belangrijke architectuurregel

R7c-3 voegt nog steeds géén parserkwaliteitsoordeel toe.

Dus:

- geen parser score;
- geen OCR confidence;
- geen auto-pass/fail;
- geen statuswijziging.

Alleen:

- fixture governance;
- deterministische IDs;
- regressiestabiliteit.

## Verwachte vervolgstap

```text
R7c-4 — supermarket parser regression runner
```

Doel:

Per canonical fixture automatisch controleren:

- store;
- datum;
- totaalbedrag;
- line count;
- parserstatus;
- explainability;
- regression deltas.

## Strategisch belang

R7c-3 markeert de overgang van:

```text
losse fixturebestanden
```

naar:

```text
beheerde regression identities
```

Dat is noodzakelijk voordat parserkwaliteit betrouwbaar en reproduceerbaar verbeterd kan worden.
