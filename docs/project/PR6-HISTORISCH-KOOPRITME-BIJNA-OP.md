# PR6 — Historische kooptermijnen koppelen aan Bijna op

TEST_LEVEL_PROVISIONAL: L
Reden: huishoudgebonden voorraadprognose en bevestigde synoniemidentiteit, backend-runtime.

## Bestaande basis (PR3/#710)
- PR3 slaat na **één herhaalaankoop** (twee verschillende dagen) direct het gemiddelde aantal dagen op per bewezen huishoudartikel/synoniemgroep.
- De huishoudinstelling voor afboeken bij herhaalaankoop en het berekenen van historische beginvoorraad worden in PR3 uitgevoerd; PR6 herschrijft, reset of migreert geen voorraad.
- Het bestaande Bijna-op-algoritme gebruikt actuele voorraad en aankoopvolume uit inventory-events en dient intact te blijven.

## PR6-uitbreiding
- Bijna op leest eenmaal per verzoek de door PR3 opgeslagen, huishoudgebonden kooptermijnen uit PostgreSQL.
- Alleen actieve artikelen, een complete en intern consistente bevestigde synoniemgroep en een bewezen koopritme (minimaal twee dagen) mogen meetellen.
- Wanneer een bestaande volumegebaseerde forecast ontbreekt, mag de bewaarde termijn gecombineerd worden met de **werkelijk geboekte hoeveelheid op de laatste bevestigde aankoopdag** en de actuele voorraad. De voorraadsituatie, de voorspel-/winkeltermijn en het minimum blijven leidend; het ritme op zichzelf veroorzaakt geen Bijna-op-signaal.
- De herhaalaankooptermijn wordt als controleerbare metadata op het Bijna-op-resultaat opgenomen. Dubbele bonnen op dezelfde dag veranderen het aantal aankoopdagen niet; bij een volumeprognose telt wel het werkelijk gekochte volume.
- Geen fuzzy naamkoppeling: zowel de kooptermijn als de aankoopevents moeten met exacte huishoudartikel-ID's overeenkomen. Groepsprognose vereist exact dezelfde vertrouwde ledenverzameling, inclusief veilige verpakkingsconversie door de bestaande Bijna-op-groepservice.
- Onbewezen, oude of ontbrekende gegevens vallen terug naar het bestaande voorraad-/event-algoritme. Een nieuwere aankoop zonder bijgewerkte kooptermijn blokkeert de oude termijn.
- Nooit historische bonnen als actuele kassabon goedkeuren, winkels opnieuw verbinden, importpauzes uitschakelen of bestaande voorraad/voorspelinstellingen wijzigen.

## Grenzen
Een huishouden met *uitsluitend historische bonnen*, maar **nog geen betrouwbaar aankoopvolume uit een actuele voorraadgebeurtenis**, krijgt het bewezen koopritme wel beschikbaar als informatie. Alleen die termijn is zonder onafhankelijk volumebewijs nog onvoldoende voor een verbruiksprognose. Een verdere, veilig te bewijzen historische hoeveelheidsbron wordt niet gegokt.

## Acceptatie
- Eerste herhaalaankoop: bestaande cadence is beschikbaar na twee dagen; forecast gebruikt exact de laatst gekochte hoeveelheid.
- Bevestigde synoniemen/verschillende winkels: dezelfde interval, zonder samenvoegen van onbetrouwbare groepen.
- Geen schijnvoorraad: geen forecast met ongeldige, negatieve of inconsistente voorraad.
- Doorlopende updates: verouderde opgeslagen termijn produceert geen nieuw signaal totdat de worker hem bijwerkt.
- De oude hoeveelheid-/minimumberekening blijft de primaire bron; geen voorraad- of databasewrites door Bijna op.
- Unitcontracten, PostgreSQL-acceptatie en reguliere F7-gates vóór Ready.
