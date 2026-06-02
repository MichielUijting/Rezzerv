# R9-28B5 — Pre-parser OCR diagnostics export

Gemaakt: `2026-05-24T20:01:30`

## SSOT-compliance

- `status_determination`: `not_performed`
- `status_service`: `receipt_status_baseline_service_v4.py`
- `parse_status_used_as_truth`: `False`
- `parser_mutated`: `False`
- `ocr_mutated`: `False`
- `database_mutated`: `False`
- `baseline_mutated`: `False`
- `ui_touched`: `False`
- `diagnostics_promoted_to_parser`: `False`

## Input

- `input_path`: `/tmp/supermarkten.zip`
- `zip_member`: `AH foto 2.jpeg`
- `filename`: `AH foto 2.jpeg`
- `mime_type_guess`: `image/jpeg`
- `original_bytes`: `151625`
- `ocr_bytes`: `1119423`

## OCR-samenvatting

- Paddle beschikbaar: `True`
- Paddle raw text items: `69`
- Paddle bounding boxes: `69`
- Paddle grouped lines: `30`
- Tesseract beschikbaar: `True`
- Tesseract lines: `30`
- Diagnostische parser-input keuze: `paddle_grouped_lines`

## Paddle gegroepeerde regels

1. `Albert Heijn Ger Koopman`
2. `Polenplein 24a Driel`
3. `tel: 026-4742394`
4. `AANTAL OMSCHRIJVING PRIJS BEDRAG`
5. `T AH M GEHAKT 6,99`
6. `T SOEPGR BASIS 1,29`
7. `2 SUBTOTAAL 8,28`
8. `JOUW VOORDEEL 0,00`
9. `waarvan`
10. `BONUS BOX 0,00`
11. `TOTAAL 8,28`
12. `BETAALD MET:`
13. `PINNEN 8,28`
14. `POI: 50100891 KLANTTICKET`
15. `Terminal BS171970 Merchant 3732071002`
16. `Periode 6085 Transactie 00093286`
17. `Token 1 1003030534301033342 V PAY`
18. `(A0000000032020) Kaart 487512xxxxxxxxx3334`
19. `Kaartserienummer 2 BETALING`
20. `Datum 26/03/2026 15:18 Autorisatiecode W01081`
21. `Totaal 8,28 EUR Contactless`
22. `Leesmethode CHIP`
23. `BTW OVER EUR`
24. `9% 7,60 0,68`
25. `TOTAAL 7,60 0.68`
26. `8521 32 107`
27. `15:18 26-03-2026`
28. `Vragen over je kassabon?`
29. `Onze kassamedewerkers`
30. `helpen je graag.`

## Tesseract regels

1. `Albert Heijn Ger Koopman`
2. `Polenplein 24a Driel`
3. `tel: 026-4742394`
4. `AANTAL OMSCHRIJVING PRIJS BEDRAG`
5. `i AH M GEHAKT 6,99`
6. `1 SOEPGR BASIS 1,29`
7. `2 SUBTOTAAL 8,28`
8. `JOUW VOORDEEL O,00`
9. `waarvan j`
10. `BONUS BOX 0,00 |`
11. `TOTAAL ss, 25`
12. `BETAALD MET:`
13. `PINNEN 8,28`
14. `POI: 50100891 KLANTTICKET`
15. `Terminal BS171970 Merchant 3732071002`
16. `Periode 6085 Transactie 00093286`
17. `Token 1003030534301033342 V PAY`
18. `(A0000000032020) Kaart 487512xxxxxxxxx3334`
19. `Kaartserienummer 2 BETALING`
20. `Datum 26/03/2026 15:18 Autorisatiecode W01081`
21. `Totaal 8,28 EUR Contactless`
22. `_ Leesmethode CHIP`
23. `BTW OVER EUR`
24. `9% 7,60 0,68`
25. `À TOTAAL 7,60 0,68`
26. `zl 107 |`
27. `sf { :`
28. `Ve yr je kassabon?`
29. `fe: Pec samedewerKers`
30. `he Je graag . Ì`

## Paddle raw items met boxes

- `0` conf=`0.9875208735466003` anchor=`(259.5, 299.0, 47.0)` text=`Albert Heijn Ger Koopman` bbox=`[299, 236, 787, 283]`
- `1` conf=`0.9667065739631653` anchor=`(299.5, 339.0, 45.0)` text=`Polenplein 24a Driel` bbox=`[339, 277, 743, 322]`
- `2` conf=`0.9794554114341736` anchor=`(337.5, 379.0, 45.0)` text=`tel: 026-4742394` bbox=`[379, 315, 708, 360]`
- `3` conf=`0.9994552135467529` anchor=`(422.0, 117.0, 40.0)` text=`AANTAL` bbox=`[117, 402, 242, 442]`
- `4` conf=`0.999354362487793` anchor=`(421.0, 278.0, 44.0)` text=`OMSCHRIJVING` bbox=`[278, 399, 531, 443]`
- `5` conf=`0.9953269958496094` anchor=`(417.5, 556.0, 49.0)` text=`PRIJS BEDRAG` bbox=`[556, 393, 811, 442]`
- `6` conf=`0.9817306399345398` anchor=`(502.5, 277.0, 41.0)` text=`AH M GEHAKT` bbox=`[277, 482, 505, 523]`
- `7` conf=`0.9970831871032715` anchor=`(497.5, 718.0, 53.0)` text=`6,99` bbox=`[718, 471, 817, 524]`
- `8` conf=`0.4579624533653259` anchor=`(505.0, 118.0, 32.0)` text=`T` bbox=`[118, 489, 137, 521]`
- `9` conf=`0.9990439414978027` anchor=`(543.5, 277.0, 41.0)` text=`SOEPGR BASIS` bbox=`[277, 523, 529, 564]`
- `10` conf=`0.9557912349700928` anchor=`(538.5, 721.0, 51.0)` text=`1,29` bbox=`[721, 513, 817, 564]`
- `11` conf=`0.4602851867675781` anchor=`(547.0, 118.0, 32.0)` text=`T` bbox=`[118, 531, 138, 563]`
- `12` conf=`0.9999327659606934` anchor=`(625.0, 112.0, 42.0)` text=`2` bbox=`[112, 604, 145, 646]`
- `13` conf=`0.9925912022590637` anchor=`(625.0, 277.0, 42.0)` text=`SUBTOTAAL` bbox=`[277, 604, 467, 646]`
- `14` conf=`0.9957828521728516` anchor=`(620.0, 721.0, 50.0)` text=`8,28` bbox=`[721, 595, 819, 645]`
- `15` conf=`0.9952101111412048` anchor=`(706.5, 113.0, 43.0)` text=`JOUW VOORDEEL` bbox=`[113, 685, 645, 728]`
- `16` conf=`0.9320977330207825` anchor=`(703.5, 725.0, 49.0)` text=`0,00` bbox=`[725, 679, 897, 728]`
- `17` conf=`0.9990052580833435` anchor=`(752.0, 275.0, 32.0)` text=`waarvan` bbox=`[275, 736, 424, 768]`
- `18` conf=`0.9963448643684387` anchor=`(789.0, 271.0, 42.0)` text=`BONUS BOX` bbox=`[271, 768, 465, 810]`
- `19` conf=`0.977285623550415` anchor=`(788.5, 721.0, 51.0)` text=`0,00` bbox=`[721, 763, 818, 814]`
- `20` conf=`0.9995691180229187` anchor=`(872.5, 109.0, 43.0)` text=`TOTAAL` bbox=`[109, 851, 359, 894]`
- `21` conf=`0.9784018993377686` anchor=`(873.0, 724.0, 50.0)` text=`8,28` bbox=`[724, 848, 900, 898]`
- `22` conf=`0.9940560460090637` anchor=`(954.5, 103.0, 41.0)` text=`BETAALD MET:` bbox=`[103, 934, 354, 975]`
- `23` conf=`0.9998820424079895` anchor=`(995.5, 267.0, 43.0)` text=`PINNEN` bbox=`[267, 974, 403, 1017]`
- `24` conf=`0.9803627729415894` anchor=`(996.5, 725.0, 49.0)` text=`8,28` bbox=`[725, 972, 822, 1021]`
- `25` conf=`0.9932782053947449` anchor=`(1080.5, 97.0, 41.0)` text=`POI: 50100891` bbox=`[97, 1060, 316, 1101]`
- `26` conf=`0.9994852542877197` anchor=`(1080.0, 569.0, 42.0)` text=`KLANTTICKET` bbox=`[569, 1059, 749, 1101]`
- `27` conf=`0.9995156526565552` anchor=`(1123.5, 97.0, 43.0)` text=`Terminal` bbox=`[97, 1102, 233, 1145]`
- `28` conf=`0.9899311661720276` anchor=`(1121.5, 407.0, 45.0)` text=`BS171970` bbox=`[407, 1099, 544, 1144]`
- `29` conf=`0.9995266795158386` anchor=`(1122.5, 567.0, 39.0)` text=`Merchant` bbox=`[567, 1103, 701, 1142]`
- `30` conf=`0.9999227523803711` anchor=`(1122.0, 839.0, 42.0)` text=`3732071002` bbox=`[839, 1101, 1007, 1143]`
- `31` conf=`0.9987508654594421` anchor=`(1168.0, 96.0, 40.0)` text=`Periode` bbox=`[96, 1148, 219, 1188]`
- `32` conf=`0.9993571639060974` anchor=`(1165.5, 471.0, 43.0)` text=`6085` bbox=`[471, 1144, 545, 1187]`
- `33` conf=`0.9994403123855591` anchor=`(1165.5, 569.0, 39.0)` text=`Transactie` bbox=`[569, 1146, 734, 1185]`
- `34` conf=`0.9992873072624207` anchor=`(1164.0, 871.0, 42.0)` text=`00093286` bbox=`[871, 1143, 1007, 1185]`
- `35` conf=`0.9983786344528198` anchor=`(1211.0, 96.0, 42.0)` text=`Token 1` bbox=`[96, 1190, 247, 1232]`
- `36` conf=`0.9995165467262268` anchor=`(1209.0, 225.0, 46.0)` text=`1003030534301033342` bbox=`[225, 1186, 544, 1232]`
- `37` conf=`0.9974611401557922` anchor=`(1207.0, 565.0, 44.0)` text=`V PAY` bbox=`[565, 1185, 658, 1229]`
- `38` conf=`0.9680975079536438` anchor=`(1253.0, 97.0, 44.0)` text=`(A0000000032020)` bbox=`[97, 1231, 364, 1275]`
- `39` conf=`0.9985322952270508` anchor=`(1250.0, 569.0, 40.0)` text=`Kaart` bbox=`[569, 1230, 662, 1270]`
- `40` conf=`0.8569442629814148` anchor=`(1248.5, 696.0, 43.0)` text=`487512xxxxxxxxx3334` bbox=`[696, 1227, 1010, 1270]`
- `41` conf=`0.9990791082382202` anchor=`(1297.5, 94.0, 45.0)` text=`Kaartserienummer` bbox=`[94, 1275, 365, 1320]`
- `42` conf=`0.5946075916290283` anchor=`(1294.5, 522.0, 39.0)` text=`2` bbox=`[522, 1275, 545, 1314]`
- `43` conf=`0.9993653297424316` anchor=`(1293.5, 568.0, 43.0)` text=`BETALING` bbox=`[568, 1272, 706, 1315]`
- `44` conf=`0.9980624914169312` anchor=`(1339.0, 276.0, 48.0)` text=`26/03/2026 15:18` bbox=`[276, 1315, 547, 1363]`
- `45` conf=`0.9992462396621704` anchor=`(1336.0, 569.0, 44.0)` text=`Autorisatiecode` bbox=`[569, 1314, 817, 1358]`
- `46` conf=`0.9967802166938782` anchor=`(1335.0, 902.0, 50.0)` text=`W01081` bbox=`[902, 1310, 1013, 1360]`
- `47` conf=`0.9991413354873657` anchor=`(1344.0, 92.0, 44.0)` text=`Datum` bbox=`[92, 1322, 185, 1366]`
- `48` conf=`0.9996201395988464` anchor=`(1387.5, 93.0, 45.0)` text=`Totaal` bbox=`[93, 1365, 196, 1410]`
- `49` conf=`0.9973757266998291` anchor=`(1382.0, 407.0, 48.0)` text=`8,28 EUR` bbox=`[407, 1358, 548, 1406]`
- `50` conf=`0.9997594356536865` anchor=`(1380.0, 566.0, 44.0)` text=`Contactless` bbox=`[566, 1358, 754, 1402]`
- `51` conf=`0.9766512513160706` anchor=`(1431.0, 91.0, 50.0)` text=`Leesmethode CHIP` bbox=`[91, 1406, 365, 1456]`
- `52` conf=`0.9992763996124268` anchor=`(1513.5, 455.0, 51.0)` text=`OVER` bbox=`[455, 1488, 553, 1539]`
- `53` conf=`0.9992391467094421` anchor=`(1509.0, 750.0, 48.0)` text=`EUR` bbox=`[750, 1485, 827, 1533]`
- `54` conf=`0.9996647834777832` anchor=`(1523.5, 86.0, 51.0)` text=`BTW` bbox=`[86, 1498, 165, 1549]`
- `55` conf=`0.9901264905929565` anchor=`(1559.5, 455.0, 55.0)` text=`7,60` bbox=`[455, 1532, 554, 1587]`
- `56` conf=`0.9553210139274597` anchor=`(1553.0, 729.0, 52.0)` text=`0,68` bbox=`[729, 1527, 827, 1579]`
- `57` conf=`0.9974933862686157` anchor=`(1569.5, 87.0, 47.0)` text=`9%` bbox=`[87, 1546, 144, 1593]`
- `58` conf=`0.9840251207351685` anchor=`(1603.5, 454.0, 55.0)` text=`7,60` bbox=`[454, 1576, 555, 1631]`
- `59` conf=`0.9240386486053467` anchor=`(1598.0, 729.0, 52.0)` text=`0.68` bbox=`[729, 1572, 828, 1624]`
- `60` conf=`0.9995561242103577` anchor=`(1615.5, 88.0, 47.0)` text=`TOTAAL` bbox=`[88, 1592, 225, 1639]`
- `61` conf=`0.9991352558135986` anchor=`(1805.0, 755.0, 48.0)` text=`107` bbox=`[755, 1781, 828, 1829]`
- `62` conf=`0.9998764991760254` anchor=`(1826.5, 409.0, 57.0)` text=`32` bbox=`[409, 1798, 473, 1855]`
- `63` conf=`0.9999650716781616` anchor=`(1829.0, 85.0, 48.0)` text=`8521` bbox=`[85, 1805, 182, 1853]`
- `64` conf=`0.9997090101242065` anchor=`(1853.5, 607.0, 61.0)` text=`26-03-2026` bbox=`[607, 1823, 829, 1884]`
- `65` conf=`0.9992058873176575` anchor=`(1868.5, 90.0, 49.0)` text=`15:18` bbox=`[90, 1844, 209, 1893]`
- `66` conf=`0.9962620735168457` anchor=`(1949.0, 287.0, 76.0)` text=`Vragen over je kassabon?` bbox=`[287, 1911, 809, 1987]`
- `67` conf=`0.9800626039505005` anchor=`(1992.0, 329.0, 62.0)` text=`Onze kassamedewerkers` bbox=`[329, 1961, 786, 2023]`
- `68` conf=`0.9447508454322815` anchor=`(2028.5, 370.0, 39.0)` text=`helpen je graag.` bbox=`[370, 2009, 714, 2048]`

## Vervolg

Use this report for R9-28B6 AH section classification on true pre-parser OCR lines and Paddle boxes.
