# Volledige officiële CBS ECOICOPv2-bijlage – bronimport

De officiële [CBS-bijlage](https://www.cbs.nl/nl-nl/longread/diversen/2026/de-ecoicopv2-indeling/bijlage) van 12 februari 2026 bevat **vijf** tabbladen:
`Toelichting`, `1-ECOICOPv2`, `2-Lijst-Speciale-Aggregaten`, `3-SA-CPI-2025=100` en `4-SA-HICP-2025=100`.

`.github/workflows/cbs-official-appendix-import.yml` downloadt de **originele** CBS-Excel, eist de eerder vastgepinde SHA-256 `6871458274be87aa0126eab1bf334365502438f5e976845df8e5c28cdf95858f`, exporteert alle niet-lege broncellen van alle vijf tabbladen inclusief bronadressen, bewaart voorloopnullen en formule-informatie, en publiceert de bron plus JSON als controleerbaar CI-artifact.

De import draait **uitsluitend in de geïsoleerde GitHub-runner**. Er is geen productie- of PO-databaseverbinding. Dit is een volledige *bronbijlage-import*, niet hetzelfde als het al mogen classificeren van producten: ouderrelaties, vijf niveaus en officiële toepassingsnotities worden nog onafhankelijk gevalideerd. De operationele `cbs_ecoicop_categories` blijft daarom leeg tot die validatie en een afzonderlijk geteste dataload plaatsvinden.

Bij afwijkende checksum, ontbrekend tabblad, lege bron of downloadfout stopt de import. Bestaande Shopify-/GS1-/product-/voorraadgegevens blijven ongemoeid. Het artifact vervalt na 30 dagen; na een succesvolle run moeten de inhoud en bronversie duurzaam op de taakbranch worden vastgelegd voordat PR #642 Ready kan worden.
