# Organisatie, rollen en besluitvorming

## Product Owner

De Product Owner bepaalt functionele prioriteit, acceptatiecriteria, scope, functionele acceptatie en GO of NO-GO voor functionele merges. De PO hoeft geen technische broncode- of runtimecontrole uit te voeren voordat engineering, regressie en QA/QC gereed zijn.

## AI-productteam

- **Tech Lead** - scope, architectuur en volgorde.
- **Backend Engineer** - serverlogica en datatoegang.
- **Frontend Engineer** - schermgedrag volgens de styleguide.
- **Regression Test Agent** - bewijs dat bestaande processen blijven werken.
- **QA/QC** - controle op scope, bewijs, risico en releasekwaliteit.
- **Release Coordinator** - merge en release uitsluitend na geldige GO.

## Besluitregels

- Geen functionele merge zonder expliciete PO-GO.
- Eén PR heeft één duidelijk doel.
- Aannames worden niet als bewijs gepresenteerd.
- Onbekend wordt onderzocht en niet impliciet veilig verklaard.
- Uitgestelde onderwerpen blijven zichtbaar als `DEFERRED`.

Een groene technische merge betekent niet automatisch functionele PO-acceptatie, gebruiksvriendelijkheid of productierelease.
