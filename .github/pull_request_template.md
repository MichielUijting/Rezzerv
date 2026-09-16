## Doel
<!-- Beschrijf één duidelijk doel voor deze PR. -->

## Scope
<!-- Wat verandert wel, en wat expliciet niet? -->

## Basis en kandidaat
- Base branch: `main`
- Base SHA: `<sha>`
- Head branch: `<branch>`
- Head SHA: `<sha>`

## Versie
- Applicatieversie: `<Rezzerv-MVP-vXX.XX.XXX of n.v.t.>`
- [ ] Versiebump is vereist en vóór Ready uitgevoerd, of aantoonbaar niet vereist
- [ ] `VERSION.txt` en alle afgeleide versiebestanden zijn synchroon

## Verplichte kandidaatcontrole
- [ ] PR heeft één doel en bevat geen scope creep
- [ ] PR is tijdens ontwikkeling Draft gebleven
- [ ] Relevante open PR's/branches die nog niet in `main` zitten zijn beoordeeld en gemeld
- [ ] Gerichte tests/contractchecks voor de wijziging zijn groen
- [ ] Normale/fast CI is groen op de definitieve kandidaat
- [ ] Definitieve head-SHA is vastgesteld vóór Ready
- [ ] Release/version preflight is groen wanneer van toepassing
- [ ] F7 / exact-candidate Full Regression is groen wanneer vereist
- [ ] Na de definitieve F7-proof is de head-SHA niet meer gewijzigd
- [ ] Geen tests, gates of contracten zijn versoepeld om groen te krijgen
- [ ] Geen secrets, persoonsgegevens, productiedata of persoonsgebonden lokale paden toegevoegd

## Testresultaten
<!-- Noteer concrete workflows/tests en uitkomsten. Geen aannames of oudere SHA's. -->

## Risico's / beperkingen
<!-- Benoem resterende risico's, niet uitgevoerde tests en bekende beperkingen. -->

## PO
- [ ] Functionele/visuele PO-controle is uitgevoerd of niet van toepassing
- [ ] De exacte mergekandidaat is aan de PO gerapporteerd
- [ ] De PO voert de merge uit; ChatGPT/Codex merge niet zelf

> Een groene CI of Ready-status is nooit zelfstandig toestemming voor release, deployment of productie-omschakeling. De mergehandeling blijft bij de PO.
