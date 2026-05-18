from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'frontend' / 'src' / 'features' / 'receipts' / 'KassaPage.jsx'
BACKUP = ROOT / 'frontend' / 'src' / 'features' / 'receipts' / 'KassaPage.jsx.bak-r5f'

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

helper_anchor = """function formatDuplicateImportMessage(result) {
  return normalizeErrorMessage(result?.duplicate_message || result?.message) || 'Deze kassabon is al eerder toegevoegd en is niet opnieuw geladen.'
}


const receiptLineTableColumns = [
"""
helper_block = """function formatDuplicateImportMessage(result) {
  return normalizeErrorMessage(result?.duplicate_message || result?.message) || 'Deze kassabon is al eerder toegevoegd en is niet opnieuw geladen.'
}

function buildReceiptPoDiagnosis(receipt) {
  const warnings = []
  const totalAmount = Number(receipt?.total_amount)
  const lineCount = Number(receipt?.line_count ?? receipt?.lines?.length ?? 0)
  const lineTotalSum = Number(receipt?.line_total_sum)
  const netLineTotalSum = Number(receipt?.net_line_total_sum)
  const storeBranch = String(receipt?.store_branch || '').trim()
  const poStatus = String(receipt?.po_norm_status || '').toLowerCase()

  if (Number.isFinite(totalAmount) && Math.abs(totalAmount) < 0.0001) {
    warnings.push('Totaalbedrag is €0,00; controleer of OCR het totaalbedrag echt heeft gevonden.')
  }
  if (lineCount <= 1) {
    warnings.push('Er is maximaal één bonregel gevonden; dit wijst vaak op een fallback of onvolledige OCR.')
  }
  if (Number.isFinite(lineTotalSum) && Number.isFinite(netLineTotalSum) && Math.abs(lineTotalSum) < 0.0001 && Math.abs(netLineTotalSum) < 0.0001 && lineCount > 0) {
    warnings.push('De som van de bonregels is €0,00; controleer of de bedragen goed zijn ingelezen.')
  }
  if (/fallback/i.test(String(receipt?.notes || ''))) {
    warnings.push('Fallback gebruikt bij het verwerken van deze bon.')
  }
  if (/totaal|btw|betaling|bankpas|pin/i.test(storeBranch)) {
    warnings.push('Vestigingsinformatie lijkt OCR-ruis te bevatten; controleer Bonkop/Bron.')
  }
  if (poStatus === 'controlled' && warnings.length) {
    warnings.push('De bon staat op Gecontroleerd, maar de diagnose adviseert extra controle.')
  }

  return [...new Set(warnings)].slice(0, 5)
}

function ReceiptPoDiagnosisCard({ receipt }) {
  const warnings = buildReceiptPoDiagnosis(receipt)
  if (!warnings.length) return null
  return (
    <div className="rz-inline-feedback rz-inline-feedback--warning" data-testid="receipt-po-diagnosis-card" style={{ display: 'grid', gap: '8px' }}>
      <div style={{ fontWeight: 700 }}>Diagnose voor controle</div>
      <ul style={{ margin: 0, paddingLeft: '20px', display: 'grid', gap: '4px' }}>
        {warnings.map((warning) => <li key={warning}>{warning}</li>)}
      </ul>
    </div>
  )
}


const receiptLineTableColumns = [
"""
if 'function buildReceiptPoDiagnosis(receipt)' not in content:
    if helper_anchor not in content:
        raise SystemExit('R5f patch aborted: helper anchor not found.')
    content = content.replace(helper_anchor, helper_block, 1)

render_anchor = """        <Tabs tabs={['Bonregels', 'Bonkop', 'Bron']} defaultTab="Bonregels" activeColor={detailAmountsMatch ? '#166534' : '#B54708'}>
"""
render_replacement = """        <ReceiptPoDiagnosisCard receipt={receipt} />

        <Tabs tabs={['Bonregels', 'Bonkop', 'Bron']} defaultTab="Bonregels" activeColor={detailAmountsMatch ? '#166534' : '#B54708'}>
"""
if '<ReceiptPoDiagnosisCard receipt={receipt} />' not in content:
    if render_anchor not in content:
        raise SystemExit('R5f patch aborted: detail tabs anchor not found.')
    content = content.replace(render_anchor, render_replacement, 1)

TARGET.write_text(content, encoding='utf-8')
print('R5f Kassa PO diagnosis patch applied to', TARGET)
print('Backup written to', BACKUP)
