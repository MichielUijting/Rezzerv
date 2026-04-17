# Rezzerv-v01.07.74 — voorraad-fixturematrix en testverwachtingen

## Bronbasis gecontroleerd
- `backend/app/main.py` → `generate_demo_data()`
- `frontend/src/features/admin/lib/browserRegressionRunner.js`
- `frontend/src/pages/Voorraad.jsx`

## Kernbevinding
De regressietestverwachting rond **Tomaten = 3** bleek niet herleidbaar als zichtbare voorraadwaarde in het scherm **Voorraad**. In de echte fixture bestaan **meerdere Tomaten-voorraadregels** en de pagina **Voorraad** aggregeert die regels op artikelnaam. Daardoor is een zichtbare enkelvoudige rij met precies `3` voor Tomaten als standaardverwachting onjuist.

## Demo-data uit `generate_demo_data()`
| Artikel | Aantal | Locatie | Sublocatie |
|---|---:|---|---|
| Tomaten | 3 | Keuken | Koelkast |
| Tomaten | 2 | Berging | Voorraadkast |
| Melk | 2 | Keuken | Koelkast |

## Deterministische aanvullingen uit `prepareRegressionFixture()`
| Artikel | Aantal | Locatie | Sublocatie |
|---|---:|---|---|
| Mosterd | 1 | Voorraad test | Plank test |
| Boormachine | 1 | Schuur | Werkbank |
| Tomaten | 3 | Voorraad test | Plank test |

## Gevolg voor zichtbare actuele voorraad
De pagina `Voorraad.jsx` gebruikt `mergeInventoryRows()` en **groepeert op genormaliseerde artikelnaam**. Daardoor worden de drie Tomaten-voorraadregels samengevoegd tot één zichtbare rij.

### Verwachte zichtbare beginstand in Voorraad
| Artikel | Verwachte zichtbare hoeveelheid |
|---|---:|
| Tomaten | 8 |
| Melk | 2 |
| Mosterd | 1 |

## Validatie van de eerder rode tests
### 1. Handmatige voorraadcorrectie
De oude test gebruikte **Tomaten** en verwachtte in het zichtscherm eerst `3`, daarna `5`. Dat is onjuist omdat Tomaten in de fixture al geaggregeerd zichtbaar is als `8`. Bovendien is de geaggregeerde rij niet geschikt als zuiver anker voor inline-editgedrag.

**Correctie:** scenario omgezet naar **Mosterd** (unieke rij, beginhoeveelheid `1`, na correctie `3`).

### 2. Nulvoorraad
De oude test gebruikte **Tomaten** als anker. Door aggregatie van meerdere Tomaten-rijen is dit geen zuiver nulvoorraadscenario.

**Correctie:** scenario omgezet naar **Mosterd** (unieke rij), zodat zichtbaar gedrag op huidig scherm en na heropenen eenduidig testbaar is.

### 3. Lidl/Jumbo/Negeren zichtbaar in Voorraad
De oude tests controleerden zichtbaarheid met alleen `ensureInventoryContainsArticle('Melk'/'Tomaten')`. Voor **Melk** is dat zwak, omdat het artikel al in de beginfixture zichtbaar is. Voor **Tomaten** is alleen zichtbaarheid nog zwakker door aggregatie.

**Correctie:** tests valideren nu de zichtbare **hoeveelheid in Voorraad** tegen de live projectie via `getInventoryQuantity(...)`, in plaats van alleen bestaan van een rij.

## Classificatie van voorraadgerelateerde regressietests
| Test | Oude aanname | Classificatie | Actie |
|---|---|---|---|
| Handmatige voorraadcorrectie blijft persistent en zichtbaar in historie | Tomaten zichtbaar als 3 | **Testverwachting fout/verouderd** | Omgezet naar Mosterd 1→3 |
| Nulvoorraad blijft zichtbaar tot Voorraad opnieuw opent | Tomaten als enkelvoudige rij | **Fixture/anker ongeschikt** | Omgezet naar Mosterd |
| Winkelwaarschuwing Negeren verwerkt alleen complete regels | Alleen bestaan van Melk in Voorraad | **Te zwakke testverwachting** | Gewijzigd naar hoeveelheidcontrole |
| Lidl-flow kan een regel koppelen en naar voorraad verwerken | Alleen bestaan van Melk in Voorraad | **Te zwakke testverwachting** | Gewijzigd naar hoeveelheidcontrole |
| Jumbo-flow kan een regel koppelen en naar voorraad verwerken | Alleen bestaan van Tomaten in Voorraad | **Naam/aggregatie-mismatch** | Gewijzigd naar hoeveelheidcontrole |

## Advies vervolg
- Eerst opnieuw regressierun draaien met deze gevalideerde verwachtingen.
- Alleen de rode voorraadtests die daarna nog overblijven, als potentiële **echte appbugs** behandelen.
