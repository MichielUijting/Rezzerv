from __future__ import annotations

from pathlib import Path

path = Path("frontend/src/features/receipts/KassaPage.jsx")
text = path.read_text(encoding="utf-8")
changes = 0

old_landing = """    if (fileKind === 'email') {
      await processEmailImportFile(file)
      return
    }
"""
new_landing = """    if (fileKind === 'email') {
      setStatus('E-mailbestand uit landingzone wordt via reguliere bestandsimport verwerkt.')
      await processReceiptFileImport(file)
      return
    }
"""
if old_landing in text:
    text = text.replace(old_landing, new_landing, 1)
    changes += 1
elif """    if (fileKind === 'email') {
      await processReceiptFileImport(file)
      return
    }
""" in text:
    text = text.replace(
        """    if (fileKind === 'email') {
      await processReceiptFileImport(file)
      return
    }
""",
        new_landing,
        1,
    )
    changes += 1
else:
    raise SystemExit("Landingzone .eml-blok niet gevonden.")

old_document_check = """    if (!isSupportedReceiptDocumentFile(file) && !isSupportedReceiptImageFile(file)) {
      setEmailRouteError('Dit bestandstype wordt in deze versie nog niet als bonbestand ondersteund. Gebruik .pdf, .zip, .png, .jpg, .jpeg, .webp of .eml.')
      setError('')
      return
    }
"""
new_document_check = """    if (!isSupportedReceiptDocumentFile(file) && !isSupportedReceiptImageFile(file) && !isSupportedEmailImportFile(file)) {
      setEmailRouteError('Dit bestandstype wordt in deze versie nog niet als bonbestand ondersteund. Gebruik .pdf, .zip, .png, .jpg, .jpeg, .webp of .eml.')
      setError('')
      return
    }
"""
if old_document_check in text:
    text = text.replace(old_document_check, new_document_check, 1)
    changes += 1
elif new_document_check in text:
    pass
else:
    raise SystemExit("Documenttype-check voor .eml niet gevonden.")

old_visibility = """            {emailRouteError && ['admin','owner'].includes(String(currentUserDisplayRole || '').trim().toLowerCase()) && (technicalUploadError?.detail || String(emailRouteError || '').startsWith('Upload mislukt. De server gaf een technische fout terug.')) ? (
              <div style={{ display: 'grid', gap: '8px' }}>
"""
new_visibility = """            {(technicalUploadError?.detail || (emailRouteError && String(emailRouteError || '').startsWith('Upload mislukt. De server gaf een technische fout terug.'))) ? (
              <div style={{ display: 'grid', gap: '8px' }}>
"""
if old_visibility in text:
    text = text.replace(old_visibility, new_visibility, 1)
    changes += 1
elif new_visibility in text:
    pass
else:
    raise SystemExit("Conditie voor technische-foutknop niet gevonden.")

old_success_message = """        setStatus(`Kassa is geladen met ${visibleReceiptCount} bon${visibleReceiptCount === 1 ? '' : 'nen'}. Er was wel een technische uploadmelding; details zijn alleen voor de admin beschikbaar.`)
"""
new_success_message = """        setStatus(`Kassa is geladen met ${visibleReceiptCount} bon${visibleReceiptCount === 1 ? '' : 'nen'}. Er was wel een technische uploadmelding; gebruik Toon technische foutmelding voor details.`)
"""
if old_success_message in text:
    text = text.replace(old_success_message, new_success_message, 1)
    changes += 1
elif new_success_message in text:
    pass
else:
    raise SystemExit("Fallbackmelding voor technische uploadfout niet gevonden.")

path.write_text(text, encoding="utf-8")
print(f"Kassa .eml runtime-diagnostiek gepatcht ({changes} wijziging(en)).")
print("Controlepunten:")
print("- landingzone .eml meldt expliciet reguliere bestandsimport")
print("- landingzone .eml gebruikt processReceiptFileImport")
print("- technische-foutknop is zichtbaar zodra technicalUploadError bestaat")
