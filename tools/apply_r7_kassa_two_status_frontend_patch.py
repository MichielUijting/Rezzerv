from pathlib import Path

path = Path("frontend/src/features/receipts/KassaPage.jsx")
text = path.read_text(encoding="utf-8")

text = text.replace("""function normalizeInboxStatus(value) {
  const normalized = String(value || '').trim()
  if (normalized === 'Gecontroleerd' || normalized === 'Controle nodig' || normalized === 'Handmatig') {
    return normalized
  }
  if (normalized === 'Nieuw' || normalized.toLowerCase() === 'manual') {
    return 'Handmatig'
  }
  return 'Handmatig'
}""", """function normalizeInboxStatus(value) {
  const normalized = String(value || '').trim()
  if (normalized === 'Gecontroleerd') return 'Gecontroleerd'
  return 'Controle nodig'
}""")

text = text.replace("""  const inboxSummary = useMemo(() => ({
    Handmatig: inboxItems.filter((item) => item.inbox_status === 'Handmatig').length,
    'Controle nodig': inboxItems.filter((item) => item.inbox_status === 'Controle nodig').length,
    Gecontroleerd: inboxItems.filter((item) => item.inbox_status === 'Gecontroleerd').length,
  }), [inboxItems])""", """  const inboxSummary = useMemo(() => ({
    'Controle nodig': inboxItems.filter((item) => item.inbox_status === 'Controle nodig').length,
    Gecontroleerd: inboxItems.filter((item) => item.inbox_status === 'Gecontroleerd').length,
  }), [inboxItems])""")

text = text.replace("""                {[
                  { key: 'Handmatig', helper: 'Handmatige beoordeling nodig' },
                  { key: 'Controle nodig', helper: 'Vraagt extra aandacht' },
                  { key: 'Gecontroleerd', helper: 'Al bekeken in Kassa' },
                ].map((entry) => {""", """                {[
                  { key: 'Controle nodig', helper: 'Vraagt extra aandacht' },
                  { key: 'Gecontroleerd', helper: 'Al bekeken in Kassa' },
                ].map((entry) => {""")

path.write_text(text, encoding="utf-8")
print("KassaPage.jsx status cleanup applied")
