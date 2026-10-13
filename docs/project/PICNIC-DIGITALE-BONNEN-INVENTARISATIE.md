# Picnic — inventarisatie digitale kassabonketen (fase 0)

Status: **analyse / voorbereiding**. Geen nieuwe runtimefunctionaliteit in deze PR.

## Opdracht en uitgangspunten

De PO wil Picnic als volgende supermarkt na AH, Lidl en Jumbo onderzoeken en
vervolgens de bestaande Picnic-keten afmaken. Hergebruik bewezen werkende
Inhuis-componenten; bouw niet opnieuw wat al beschikbaar is. Deze inventarisatie
is gebaseerd op repository `main` bij aanvang: `e5e4614589dde162fb52e594c1d20356133287d6`.

## Aantoonbaar aanwezige onderdelen

| Onderdeel | Bron | Vastgesteld |
| --- | --- | --- |
| Picnic EML upload | `frontend/src/features/receipts/KassaPage.jsx` (`uploadPicnicEmailReceiptFile`, `processPicnicEmailLandingFile`) | In Kassa is een aparte .eml-route aangesloten met uploadprogressie, duplicaatmelding, inbox-refresh en detailopening. |
| Picnic API | `POST /api/receipts/picnic-email-import`; `backend/app/api/picnic_email_import_source_closure.py` | Vereist geautoriseerd huishouden, niet-leeg .eml-bestand en opgeslagen canonieke e-mailbron; roept centrale `ingest_receipt` aan. |
| E-mailparsing | `backend/app/main.py`: `parse_email_receipt_payload` | Extraheert afzender, onderwerp, body en bijlagen. Prefereert PDF, daarna afbeelding, daarna HTML-/tekstinhoud. |
| Gedeelde e-mailverwerking | `backend/app/main.py`: `import_email_receipt_payload` | Kan geselecteerde inhoud via centrale kassabonservice verwerken, e-mailmetadata bewaren en waar nodig reparsing proberen. |
| Gmail OAuth | `backend/app/main.py`: `/api/receipts/gmail/connect-url`, `/callback`, `/sync`; `receipt_gmail_oauth_household_guard.py` | Huishoudgebonden OAuth-route en gelabelde Gmail-berichtenimport bestaan. Geen Picnic-specifieke automatische labeling aangetoond. |
| Gmail deduplicatie | `has_processed_gmail_message`, `store_gmail_import_result` | Per huishouden + Gmail-message-ID geregistreerd. Centrale kassabonduplicaten staan los van deze message-ID. |
| Testmateriaal | `backend/app/testing/kassa_regression/raw/picnic_app_1.eml` t/m `picnic_app_4.eml` | Vier opgeslagen Picnic-testbestanden aanwezig; hun actuele financiële uitkomsten zijn hiermee nog niet vastgesteld. |
| Kassa-documentstroom | `frontend/src/features/receipts/KassaPage.jsx` | Import kan bon in Kassa tonen en detail openen; downstream Uitpakken → Voorraad is voor Picnic nog niet specifiek bewezen. |

## Openstaande technisch/functionele onderzoeksvragen

1. **Verwerking van brongegevens:** verifieer bij de vier bestaande Picnic-fixtures
   of artikelen, aantallen, regelprijzen, bezorgkosten, korting, statiegeld,
   totaal, aankoopdatum en bonidentiteit overeenkomen met de bron.
   Regels die in het bronformaat niet voorkomen, niet verzinnen.
2. **Specifieke import vs. generieke e-mail:** de Picnic-endpoint voert de
   ruwe .eml via `ingest_receipt` in en bewaart `parse_email_receipt_payload`
   metadata. De gedeelde `import_email_receipt_payload` kan daarentegen PDF-
   of afbeeldingsbijlagen selecteren en reparsing uitvoeren.
   Vergelijk met gerichte tests of deze twee routes op identieke bonnen dezelfde
   artikel-, totaal- en duplicaatuitkomst geven. Geen stilzwijgende vervanging
   van de bestaande route zonder bewijs.
3. **Automatische Gmail-import:** de bestaande sync leest alleen mails met het
   ingestelde Gmail-label en synchroniseert op verzoek; er is geen bewezen
   automatische Picnic-afzenderherkenning, labeling of periodieke synchronisatie
   aangetoond. Leg die vraag expliciet naast het bestaande Gmail-OAuth-contract.
4. **Herkomstbeveiliging:** alleen een `From`-header of e-mailadres bewijst
   geen authenticiteit. Verwerk geen Picnic-specifiek vertrouwensniveau zonder
   aanvullende verificatie; gebruik de bestaande privacy- en householdgrenzen.
5. **Dubbelgebruik:** toets herimport van exact dezelfde bronbon via Picnic
   handmatig, gedeelde e-mail en Gmail; voorkom duplicaten in Kassa onafhankelijk
   van bestandsnaam of Gmail-message-ID.
6. **End-to-end:** bewijs Kassa → Uitpakken → Voorraad voor geslaagde bonnen,
   inclusief reparatiepad voor niet-herkende regels en foutstatus.
7. **PO-bediening:** beslis pas na tests of Picnic onder Winkelkoppelingen als
   werkende digitale koppeling mag worden getoond; toon geen fictieve
   accountherkenning of automatische synchronisatie.

## Voorgestelde uitvoeringsvolgorde in vervolgontwikkeling

- Fase A: gerichte read-only fixture-/routevergelijking; objectieve groen/rood-matrix
  op bestaande vier EML-bonnen. Controleer ontbrekende bronvelden afzonderlijk.
- Fase B: repareer alleen gevonden Picnic-parser/importafwijkingen, met
  regressietest per bewezen fout. Bestaande centrale componenten hergebruiken.
- Fase C: test import, herimport/duplicaatstatus en Uitpakken/Voorraad in een
  testomgeving. Geen bestaande lokale gebruikersdata wissen.
- Fase D: onderzoek Picnic-mailherkenning via de bestaande Gmail-route. Alleen
  implementeren bij bewezen veilig en geautoriseerd huishoudpad; geen
  ongedocumenteerde Picnic-account-API aannemen.
- Fase E: lokale PO-test via het bewezen Inhuis-éénklikscriptpatroon, met
  veilige Git-branch/SHA-controle, daarna definitieve patchversie,
  Ready/preflight, vereiste F7 exact-candidate en afzonderlijke PO-GO.

## Acceptatiecriteria voor de implementatiefase

- Alle gekozen Picnic-fixtures tonen herleidbare productregels en totalen of
  expliciete `review_needed` zonder foutieve succesclaim.
- Dubbele bronbon wordt niet tweemaal als nieuwe bon toegevoegd.
- Ontvangst, eventuele parsefout, gedeeltelijke verwerking en vervolgstappen
  zijn zichtbaar in Kassa.
- De bestaande AH-, Lidl- en Jumbo-koppelingen blijven onaangetast.
- De Picnic-keten Kassa → Uitpakken → Voorraad is aantoonbaar gevalideerd;
  automatische Gmail-synchronisatie wordt apart geaccepteerd als die haalbaar is.

## Repositorygates

Alleen documentatie in deze inventarisatie-PR; daarom **geen patchversiebump**
en geen nieuwe runtime-/CI-claims. PR blijft Draft. Implementatie mag pas
als de scope en tests verder zijn uitgewerkt. Voor latere runtimewijzigingen
volgen de reguliere versie-/testregels en exact-candidate-gates. Merge vereist
expliciete PO-GO voor de actuele kandidaat, release/deployment een aparte GO.
