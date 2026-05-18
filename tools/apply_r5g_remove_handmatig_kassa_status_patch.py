from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'frontend' / 'src' / 'features' / 'receipts' / 'KassaPage.jsx'
BACKUP = ROOT / 'frontend' / 'src' / 'features' / 'receipts' / 'KassaPage.jsx.bak-r5g'

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

old_normalize = """function normalizeInboxStatus(value) {
  const normalized = String(value || '').trim()
  if (normalized === 'Gecontroleerd' || normalized === 'Controle nodig' || normalized === 'Handmatig') {
    return normalized
  }
  if (normalized === 'Nieuw' || normalized.toLowerCase() === 'manual') {
    return 'Handmatig'
  }
  return 'Handmatig'
}


function inboxStatusAccentColor(value) {
  if (value === 'Gecontroleerd') return '#12B76A'
  if (value === 'Controle nodig') return '#F79009'
  return '#B54708'
}
"""

new_normalize = """function normalizeInboxStatus(value) {
  const normalized = String(value || '').trim()
  if (normalized === 'Gecontroleerd' || normalized === 'Controle nodig') {
    return normalized
  }
  return 'Controle nodig'
}


function inboxStatusAccentColor(value) {
  if (value === 'Gecontroleerd') return '#12B76A'
  return '#F79009'
}
"""

if old_normalize not in content:
    raise SystemExit('R5g patch aborted: normalizeInboxStatus block not found.')
content = content.replace(old_normalize, new_normalize, 1)

old_summary = """  const inboxSummary = useMemo(() => ({
    Handmatig: inboxItems.filter((item) => item.inbox_status === 'Handmatig').length,
    'Controle nodig': inboxItems.filter((item) => item.inbox_status === 'Controle nodig').length,
    Gecontroleerd: inboxItems.filter((item) => item.inbox_status === 'Gecontroleerd').length,
  }), [inboxItems])
"""

new_summary = """  const inboxSummary = useMemo(() => ({
    'Controle nodig': inboxItems.filter((item) => item.inbox_status === 'Controle nodig').length,
    Gecontroleerd: inboxItems.filter((item) => item.inbox_status === 'Gecontroleerd').length,
  }), [inboxItems])
"""

if old_summary not in content:
    raise SystemExit('R5g patch aborted: inboxSummary block not found.')
content = content.replace(old_summary, new_summary, 1)

old_intro = """                    Zie direct welke bonnen nieuw zijn, controle nodig hebben of al gecontroleerd zijn.
"""
new_intro = """                    Zie direct welke bonnen controle nodig hebben of al gecontroleerd zijn.
"""
if old_intro in content:
    content = content.replace(old_intro, new_intro, 1)

old_cards = """                {[
                  { key: 'Handmatig', helper: 'Handmatige beoordeling nodig' },
                  { key: 'Controle nodig', helper: 'Vraagt extra aandacht' },
                  { key: 'Gecontroleerd', helper: 'Al bekeken in Kassa' },
                ].map((entry) => {
"""
new_cards = """                {[
                  { key: 'Controle nodig', helper: 'Vraagt extra aandacht' },
                  { key: 'Gecontroleerd', helper: 'Al bekeken in Kassa' },
                ].map((entry) => {
"""
if old_cards not in content:
    raise SystemExit('R5g patch aborted: status card list not found.')
content = content.replace(old_cards, new_cards, 1)

old_shadow = """                        boxShadow: isActive ? `0 0 0 3px ${entry.key === 'Gecontroleerd' ? 'rgba(18,183,106,0.12)' : entry.key === 'Controle nodig' ? 'rgba(247,144,9,0.12)' : 'rgba(181,71,8,0.12)'}` : 'none',
"""
new_shadow = """                        boxShadow: isActive ? `0 0 0 3px ${entry.key === 'Gecontroleerd' ? 'rgba(18,183,106,0.12)' : 'rgba(247,144,9,0.12)'}` : 'none',
"""
if old_shadow in content:
    content = content.replace(old_shadow, new_shadow, 1)

old_row_shadow = """                            boxShadow: `inset 4px 0 0 ${item.inbox_status === 'Gecontroleerd' ? '#12B76A' : item.inbox_status === 'Controle nodig' ? '#F79009' : '#B54708'}`,
"""
new_row_shadow = """                            boxShadow: `inset 4px 0 0 ${item.inbox_status === 'Gecontroleerd' ? '#12B76A' : '#F79009'}`,
"""
if old_row_shadow not in content:
    raise SystemExit('R5g patch aborted: row status color expression not found.')
content = content.replace(old_row_shadow, new_row_shadow, 1)

if "'Handmatig'" in content or 'Handmatige beoordeling nodig' in content:
    raise SystemExit('R5g patch aborted: Handmatig still present in KassaPage.jsx after patch.')

TARGET.write_text(content, encoding='utf-8')
print('R5g removed Handmatig Kassa status from', TARGET)
print('Backup written to', BACKUP)
