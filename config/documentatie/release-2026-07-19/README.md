# Rezzerv-documentatie release 2026-07-19

Deze map bevat de door QA/QC en PO bijgewerkte Rezzerv-projectdocumentatie van 19 juli 2026, aangevuld met de normatieve ketentestdocumentatie voor huishouden `0`.

## Archief

- `Rezzerv-documentatie_bijgewerkt_2026-07-19.zip`

## Basisdocumenten

- Rezzerv-Functioneel-Ontwerp-Volledig-Release-4_v4.12.docx
- Rezzerv-Technisch-Ontwerp-Volledig-Release-4_v4.13.docx
- Rezzerv-QA-QC-handvest v10.docx
- Rezzerv_Doelarchitectuur_Platform_Release-4_v2.22.docx
- Rezzerv_Opstartroutine_v1.12.docx
- Rezzerv-Development-Stack_v1.14.docx
- Rezzerv-Werkinstructies-AI_v9.md
- UPDATE-SAMENVATTING_2026-07-18.md

## Normatieve aanvullingen ketentest

De volgende aanvullingen zijn integraal onderdeel van de genoemde basisdocumenten en gaan voor wanneer de oudere versie de nieuwe ketentest nog niet vermeldt:

- `Rezzerv_Opstartroutine_v1.13_Aanvulling_Ketentest.md`
  - verplicht uitvoermoment;
  - commando's voor de runner;
  - geldige groene markers;
  - merge- en release-gate;
  - expliciete testcontext huishouden `0`.
- `Rezzerv_Technisch_Ontwerp_v4.14_Aanvulling_Ketentest.md`
  - technische testarchitectuur;
  - tijdelijke geisoleerde database;
  - productiecode en productieservices;
  - voorraad-, event-, Producttype-, Spaartegoeden- en Bijna-opcontroles;
  - huidige beperkingen en vervolgstappen.

## Normatieve runner en tests

- `scripts/run-receipt-inventory-chain-v2.ps1`
- `backend/app/testing/receipt_inventory_production_chain.py`
- `backend/app/testing/product_type_link_contract.py`

De ketentest is verplicht bij wijzigingen aan Kassa, Uitpakken, universele artikelen, huishoudartikelen, Producttype, inventory-events, Voorraad, Bijna op en spaar- of koopzegelclassificatie. Een rode ketentest betekent automatisch **NO-GO**.

De documenten beschrijven daarnaast onder meer de kassabonketen, universele artikelen, Artikelgroepen, Producttypes, de PowerShell-runner en de verplichte merge-gate.