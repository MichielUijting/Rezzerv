from __future__ import annotations

from pathlib import Path

path = Path("frontend/src/features/receipts/KassaPage.jsx")
text = path.read_text(encoding="utf-8")
changes = 0

old = """  const poNormStatusLabel = String(receipt?.po_norm_status_label ?? receipt?.status_label ?? receipt?.norm_status_label ?? '').trim().toLowerCase()
  const isPoNormControlled = poNormStatusLabel === 'gecontroleerd'
  const detailAmountsMatch = Number.isFinite(Number(headerDraft.total_amount)) && lines.length > 0 && Math.abs(Number(headerDraft.total_amount) - visibleNetTotalSum) < 0.01
  const detailAmountsAccepted = detailAmountsMatch || isPoNormControlled
  const totalsMismatchWarningVisible = !detailAmountsAccepted && Number.isFinite(Number(headerDraft.total_amount)) && lines.length > 0
"""
new = """  const poNormStatusLabel = String(receipt?.po_norm_status_label ?? receipt?.status_label ?? receipt?.norm_status_label ?? '').trim().toLowerCase()
  const isPoNormControlled = poNormStatusLabel === 'gecontroleerd'
  const receiptStoreName = String(receipt?.store_name || '').trim().toLowerCase()
  const isPicnicReceipt = receiptStoreName.includes('picnic')
  const detailAmountsMatch = Number.isFinite(Number(headerDraft.total_amount)) && lines.length > 0 && Math.abs(Number(headerDraft.total_amount) - visibleNetTotalSum) < 0.01
  const detailAmountsAccepted = detailAmountsMatch || isPoNormControlled || isPicnicReceipt
  const totalsMismatchWarningVisible = !isPicnicReceipt && !detailAmountsAccepted && Number.isFinite(Number(headerDraft.total_amount)) && lines.length > 0
"""
if old not in text:
    raise SystemExit("Detailbedrag-validatieblok niet gevonden; patch niet uitgevoerd.")
text = text.replace(old, new, 1)
changes += 1

old = """            <div style={{ color: detailAmountsAccepted ? '#027A48' : '#B54708', fontWeight: 600 }}>{detailAmountsAccepted ? 'Bonbedragen sluiten aan' : 'Totaalbedrag wijkt af van de bonregels'}</div>
            {totalsMismatchWarningVisible ? <div style={{ color: '#B54708', fontSize: 13 }}>Je kunt deze afwijking overrulen via â€˜Goedkeuren voor Uitpakkenâ€™. De bon gaat dan naar Gecontroleerd.</div> : null}
"""
new = """            <div style={{ color: detailAmountsAccepted ? '#027A48' : '#B54708', fontWeight: 600 }}>{isPicnicReceipt ? 'Picnic: totaalbedrag wordt niet als controlecriterium gebruikt' : (detailAmountsAccepted ? 'Bonbedragen sluiten aan' : 'Totaalbedrag wijkt af van de bonregels')}</div>
            {totalsMismatchWarningVisible ? <div style={{ color: '#B54708', fontSize: 13 }}>Je kunt deze afwijking overrulen via 'Goedkeuren voor Uitpakken'. De bon gaat dan naar Gecontroleerd.</div> : null}
"""
if old not in text:
    raise SystemExit("Detailmeldingblok met mojibake niet gevonden; patch niet uitgevoerd.")
text = text.replace(old, new, 1)
changes += 1

path.write_text(text, encoding="utf-8")
print(f"Picnic detailbedrag-validatie aangepast ({changes} wijzigingen).")
print("- Picnic accepteert detailbedragen zonder totaalbedragmatch")
print("- Picnic toont geen mismatchwaarschuwing")
print("- Mojibake in de Goedkeuren-tekst is verwijderd")
