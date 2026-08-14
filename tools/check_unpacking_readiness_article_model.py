from pathlib import Path

SOURCE = Path('frontend/src/features/stores/StoreBatchDetailPage.jsx')
text = SOURCE.read_text(encoding='utf-8')

# Artikelgroep is optioneel voor Uitpakken -> Voorraad.
assert '&& hasArticleGroup\n    && hasValidLocation' not in text, (
    'Artikelgroep blokkeert nog steeds de Uitpakken-readiness.'
)
assert "statusReason = 'Artikelgroep ontbreekt.'" not in text, (
    'Artikelgroep wordt nog steeds als blokkerende statusreden gebruikt.'
)
assert 'artikel/product, locatie of artikelgroep' not in text, (
    'De gebruikersmelding noemt Artikelgroep nog steeds als verplichte voorwaarde.'
)

# Een onbekend bonartikel mag een huishoudartikel krijgen zonder artikelgroep
# en ongeacht of er al een universele productmatch bestaat.
assert '&& hasArticleGroup\n          && hasValidLocation' not in text, (
    'Automatisch aanmaken van het huishoudartikel vereist nog steeds Artikelgroep.'
)
assert '&& !hasGlobalProduct\n          && hasRawArticleName' not in text, (
    'Een bestaande universele productmatch blokkeert nog steeds het aanmaken van het huishoudartikel.'
)

# UI: Mijn artikel verdwijnt als zichtbare hoofdterm uit de bonregel-tabel/detail.
assert '>Mijn artikel</ResizableHeaderCell>' not in text, (
    'De hoofdtabel toont nog steeds Mijn artikel.'
)
assert '<dt>Mijn artikel</dt>' not in text, (
    'Bonartikeldetails tonen nog steeds Mijn artikel als gebruikersveld.'
)

# Artikelgroep blijft zichtbaar en optioneel; leeg is een geldige keuze.
assert '>Artikelgroep</ResizableHeaderCell>' in text, (
    'De hoofdtabel toont Artikelgroep nog niet.'
)
assert '<option value="">Niet ingedeeld</option>' in text, (
    'Artikelgroep heeft geen expliciete geldige Niet ingedeeld-keuze.'
)

print('UNPACKING_READINESS_ARTICLE_MODEL_CONTRACT_GREEN')
