# R9-28B5 — Pre-parser OCR diagnostics export

Gemaakt: `2026-05-24T20:01:56`

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
- `zip_member`: `AH foto 3.jpg`
- `filename`: `AH foto 3.jpg`
- `mime_type_guess`: `image/jpeg`
- `original_bytes`: `3540025`
- `ocr_bytes`: `3774937`

## OCR-samenvatting

- Paddle beschikbaar: `True`
- Paddle raw text items: `70`
- Paddle bounding boxes: `70`
- Paddle grouped lines: `23`
- Tesseract beschikbaar: `True`
- Tesseract lines: `3`
- Diagnostische parser-input keuze: `paddle_grouped_lines`

## Paddle gegroepeerde regels

1. `1`
2. `Albert Heijn`
3. `Albert Heiin to go Station Groningen`
4. `Telefoon 050-3135315 PRIJS BEDRAG`
5. `OMSCHRIJVING 1,80 3,60`
6. `AANTAL CHAUDF WATER AH SANDWICH 5,40`
7. `1 SUBTOTAAL 0,00`
8. `2 VOORDEEL 0,00`
9. `JE App Deals waarvan 5,40`
10. `TE BETALEN 5,40`
11. `BETAALD MET: PINNEN 57W83B 9131`
12. `KLANTTICKET POI: 50047284 2002376 VPAY Periode Terminal y`
13. `(A0000000032020) Merchant Transactie 01882667 V-PAY Kaartserienummer 11/05/2019 08:09`
14. `Kaart xxxxxxxxxxxxxxx5103 Totaal Datum 5,40 EUR`
15. `Autorisatiecode BETALING X1J9U8`
16. `Leesmethode NFC Chip OVER 0,45 EUR`
17. `9% BTW 4,95 4,95 0.45`
18. `TOTAAL 17 713`
19. `5826 63 11-05-2019`
20. `08:09`
21. `Download nu de AH to go app!`
22. `Spaar automatisch en krijg`
23. `gratis een product.`

## Tesseract regels

1. `oh`
2. `Seu ce lee tan Sa oral el ae a`
3. `pa Fe`

## Paddle raw items met boxes

- `0` conf=`0.9456163644790649` anchor=`(452.5, 940.0, 871.0)` text=`1` bbox=`[940, 17, 1719, 888]`
- `1` conf=`0.9920831322669983` anchor=`(863.5, 641.0, 123.0)` text=`Albert Heijn` bbox=`[641, 802, 918, 925]`
- `2` conf=`0.9664329886436462` anchor=`(944.0, 540.0, 174.0)` text=`Albert Heiin to go` bbox=`[540, 857, 1008, 1031]`
- `3` conf=`0.9957257509231567` anchor=`(990.5, 568.0, 171.0)` text=`Station Groningen` bbox=`[568, 905, 1012, 1076]`
- `4` conf=`0.9993870258331299` anchor=`(1043.5, 1049.0, 101.0)` text=`BEDRAG` bbox=`[1049, 993, 1235, 1094]`
- `5` conf=`0.9870713949203491` anchor=`(1041.5, 527.0, 195.0)` text=`Telefoon 050-3135315` bbox=`[527, 944, 1043, 1139]`
- `6` conf=`0.9985175132751465` anchor=`(1097.5, 873.0, 89.0)` text=`PRIJS` bbox=`[873, 1053, 1027, 1142]`
- `7` conf=`0.9653618335723877` anchor=`(1142.0, 1115.0, 88.0)` text=`1,80` bbox=`[1115, 1098, 1247, 1186]`
- `8` conf=`0.9461541175842285` anchor=`(1196.0, 1117.0, 90.0)` text=`3,60` bbox=`[1117, 1151, 1254, 1241]`
- `9` conf=`0.9982190132141113` anchor=`(1179.0, 510.0, 140.0)` text=`OMSCHRIJVING` bbox=`[510, 1109, 827, 1249]`
- `10` conf=`0.9994504451751709` anchor=`(1263.0, 275.0, 94.0)` text=`AANTAL` bbox=`[275, 1216, 437, 1310]`
- `11` conf=`0.9605472683906555` anchor=`(1303.0, 1123.0, 94.0)` text=`5,40` bbox=`[1123, 1256, 1265, 1350]`
- `12` conf=`0.9964262843132019` anchor=`(1284.0, 519.0, 132.0)` text=`CHAUDF WATER` bbox=`[519, 1218, 834, 1350]`
- `13` conf=`0.9870110154151917` anchor=`(1338.5, 523.0, 125.0)` text=`AH SANDWICH` bbox=`[523, 1276, 815, 1401]`
- `14` conf=`0.9882797002792358` anchor=`(1431.5, 299.0, 47.0)` text=`1` bbox=`[299, 1408, 331, 1455]`
- `15` conf=`0.9342355728149414` anchor=`(1420.5, 1027.0, 119.0)` text=`0,00` bbox=`[1027, 1361, 1271, 1480]`
- `16` conf=`0.9991970062255859` anchor=`(1448.5, 529.0, 109.0)` text=`SUBTOTAAL` bbox=`[529, 1394, 765, 1503]`
- `17` conf=`0.8750182390213013` anchor=`(1515.0, 1139.0, 90.0)` text=`0,00` bbox=`[1139, 1470, 1280, 1560]`
- `18` conf=`0.9995343685150146` anchor=`(1534.0, 301.0, 54.0)` text=`2` bbox=`[301, 1507, 341, 1561]`
- `19` conf=`0.9990663528442383` anchor=`(1552.0, 440.0, 154.0)` text=`VOORDEEL` bbox=`[440, 1475, 842, 1629]`
- `20` conf=`0.9882781505584717` anchor=`(1623.5, 304.0, 77.0)` text=`JE` bbox=`[304, 1585, 418, 1662]`
- `21` conf=`0.9982267022132874` anchor=`(1611.5, 533.0, 85.0)` text=`waarvan` bbox=`[533, 1569, 723, 1654]`
- `22` conf=`0.9947664737701416` anchor=`(1653.5, 531.0, 111.0)` text=`App Deals` bbox=`[531, 1598, 777, 1709]`
- `23` conf=`0.9157187938690186` anchor=`(1691.5, 1039.0, 125.0)` text=`5,40` bbox=`[1039, 1629, 1292, 1754]`
- `24` conf=`0.9826812744140625` anchor=`(1848.5, 1155.0, 99.0)` text=`5,40` bbox=`[1155, 1799, 1306, 1898]`
- `25` conf=`0.9967076182365417` anchor=`(1831.5, 304.0, 163.0)` text=`TE BETALEN` bbox=`[304, 1750, 804, 1913]`
- `26` conf=`0.9959149956703186` anchor=`(1961.0, 283.0, 112.0)` text=`BETAALD MET:` bbox=`[283, 1905, 591, 2017]`
- `27` conf=`0.9993560314178467` anchor=`(1977.0, 523.0, 88.0)` text=`PINNEN` bbox=`[523, 1933, 701, 2021]`
- `28` conf=`0.9958665370941162` anchor=`(1987.0, 1299.0, 92.0)` text=`57W83B` bbox=`[1299, 1941, 1461, 2033]`
- `29` conf=`0.9974250793457031` anchor=`(2037.5, 1347.0, 85.0)` text=`9131` bbox=`[1347, 1995, 1466, 2080]`
- `30` conf=`0.9977413415908813` anchor=`(2072.0, 845.0, 88.0)` text=`Terminal` bbox=`[845, 2028, 1029, 2116]`
- `31` conf=`0.9823496341705322` anchor=`(2123.5, 270.0, 99.0)` text=`POI: 50047284` bbox=`[270, 2074, 541, 2173]`
- `32` conf=`0.9915615916252136` anchor=`(2127.0, 844.0, 82.0)` text=`Periode` bbox=`[844, 2086, 1014, 2168]`
- `33` conf=`0.9995514154434204` anchor=`(2158.5, 659.0, 81.0)` text=`2002376` bbox=`[659, 2118, 824, 2199]`
- `34` conf=`0.995248556137085` anchor=`(2175.5, 266.0, 93.0)` text=`KLANTTICKET` bbox=`[266, 2129, 502, 2222]`
- `35` conf=`0.9931744337081909` anchor=`(2181.0, 842.0, 76.0)` text=`VPAY` bbox=`[842, 2143, 974, 2219]`
- `36` conf=`0.29586198925971985` anchor=`(2195.5, 1443.0, 49.0)` text=`y` bbox=`[1443, 2171, 1471, 2220]`
- `37` conf=`0.9981951713562012` anchor=`(2212.5, 637.0, 87.0)` text=`01882667` bbox=`[637, 2169, 826, 2256]`
- `38` conf=`0.9975279569625854` anchor=`(2230.5, 262.0, 83.0)` text=`Merchant` bbox=`[262, 2189, 440, 2272]`
- `39` conf=`0.9959319829940796` anchor=`(2232.5, 845.0, 73.0)` text=`V-PAY` bbox=`[845, 2196, 975, 2269]`
- `40` conf=`0.9896464347839355` anchor=`(2276.0, 265.0, 82.0)` text=`Transactie` bbox=`[265, 2235, 474, 2317]`
- `41` conf=`0.9962120056152344` anchor=`(2267.5, 847.0, 109.0)` text=`Kaartserienummer` bbox=`[847, 2213, 1218, 2322]`
- `42` conf=`0.9916741847991943` anchor=`(2280.0, 1095.0, 120.0)` text=`11/05/2019 08:09` bbox=`[1095, 2220, 1482, 2340]`
- `43` conf=`0.9673361778259277` anchor=`(2313.5, 260.0, 103.0)` text=`(A0000000032020)` bbox=`[260, 2262, 590, 2365]`
- `44` conf=`0.9916777610778809` anchor=`(2325.0, 1275.0, 102.0)` text=`5,40 EUR` bbox=`[1275, 2274, 1490, 2376]`
- `45` conf=`0.9991072416305542` anchor=`(2340.0, 847.0, 72.0)` text=`Datum` bbox=`[847, 2304, 976, 2376]`
- `46` conf=`0.8497604131698608` anchor=`(2346.0, 250.0, 144.0)` text=`Kaart xxxxxxxxxxxxxxx5103` bbox=`[250, 2274, 823, 2418]`
- `47` conf=`0.9977355599403381` anchor=`(2393.5, 845.0, 79.0)` text=`Totaal` bbox=`[845, 2354, 992, 2433]`
- `48` conf=`0.9373120665550232` anchor=`(2418.0, 669.0, 84.0)` text=`X1J9U8` bbox=`[669, 2376, 826, 2460]`
- `49` conf=`0.99949711561203` anchor=`(2429.0, 248.0, 80.0)` text=`BETALING` bbox=`[248, 2389, 428, 2469]`
- `50` conf=`0.986548125743866` anchor=`(2471.0, 244.0, 100.0)` text=`Autorisatiecode` bbox=`[244, 2421, 564, 2521]`
- `51` conf=`0.9992694854736328` anchor=`(2517.0, 1222.0, 84.0)` text=`EUR` bbox=`[1222, 2475, 1342, 2559]`
- `52` conf=`0.9815024137496948` anchor=`(2519.0, 238.0, 126.0)` text=`Leesmethode NFC Chip` bbox=`[238, 2456, 669, 2582]`
- `53` conf=`0.9989830851554871` anchor=`(2579.0, 747.0, 84.0)` text=`OVER` bbox=`[747, 2537, 889, 2621]`
- `54` conf=`0.895814061164856` anchor=`(2588.0, 1194.0, 92.0)` text=`0,45` bbox=`[1194, 2542, 1347, 2634]`
- `55` conf=`0.9963338971138` anchor=`(2654.0, 225.0, 76.0)` text=`BTW` bbox=`[225, 2616, 333, 2692]`
- `56` conf=`0.9893243908882141` anchor=`(2646.0, 746.0, 90.0)` text=`4,95` bbox=`[746, 2601, 891, 2691]`
- `57` conf=`0.8850430846214294` anchor=`(2656.5, 1197.0, 95.0)` text=`0.45` bbox=`[1197, 2609, 1354, 2704]`
- `58` conf=`0.9789177179336548` anchor=`(2717.5, 224.0, 71.0)` text=`9%` bbox=`[224, 2682, 302, 2753]`
- `59` conf=`0.9953416585922241` anchor=`(2712.5, 747.0, 91.0)` text=`4,95` bbox=`[747, 2667, 894, 2758]`
- `60` conf=`0.998900830745697` anchor=`(2774.5, 225.0, 87.0)` text=`TOTAAL` bbox=`[225, 2731, 402, 2818]`
- `61` conf=`0.9974033832550049` anchor=`(2787.5, 1273.0, 87.0)` text=`713` bbox=`[1273, 2744, 1398, 2831]`
- `62` conf=`0.9823554754257202` anchor=`(2824.0, 963.0, 82.0)` text=`17` bbox=`[963, 2783, 1048, 2865]`
- `63` conf=`0.9987043142318726` anchor=`(2870.0, 550.0, 76.0)` text=`63` bbox=`[550, 2832, 633, 2908]`
- `64` conf=`0.978204607963562` anchor=`(2875.5, 1035.0, 107.0)` text=`11-05-2019` bbox=`[1035, 2822, 1370, 2929]`
- `65` conf=`0.9984458684921265` anchor=`(2907.0, 221.0, 82.0)` text=`5826` bbox=`[221, 2866, 355, 2948]`
- `66` conf=`0.9903243780136108` anchor=`(2971.5, 224.0, 87.0)` text=`08:09` bbox=`[224, 2928, 386, 3015]`
- `67` conf=`0.970621645450592` anchor=`(3057.0, 429.0, 152.0)` text=`Download nu de AH to go app!` bbox=`[429, 2981, 1281, 3133]`
- `68` conf=`0.9528233408927917` anchor=`(3130.0, 469.0, 146.0)` text=`Spaar automatisch en krijg` bbox=`[469, 3057, 1271, 3203]`
- `69` conf=`0.9870443940162659` anchor=`(3198.0, 599.0, 114.0)` text=`gratis een product.` bbox=`[599, 3141, 1177, 3255]`

## Vervolg

Use this report for R9-28B6 AH section classification on true pre-parser OCR lines and Paddle boxes.
