from __future__ import annotations

from pathlib import Path

path = Path("frontend/src/features/receipts/KassaPage.jsx")
text = path.read_text(encoding="utf-8")
changes = 0

old = """    if (!isSupportedReceiptDocumentFile(file) && !isSupportedReceiptImageFile(file)) {
      setEmailRouteError('Dit bestandstype wordt in deze versie nog niet als bonbestand ondersteund. Gebruik .pdf, .zip, .png, .jpg, .jpeg, .webp of .eml.')
      setError('')
      return
    }
"""
new = """    if (!isSupportedReceiptDocumentFile(file) && !isSupportedReceiptImageFile(file) && !isSupportedEmailImportFile(file)) {
      setEmailRouteError('Dit bestandstype wordt in deze versie nog niet als bonbestand ondersteund. Gebruik .pdf, .zip, .png, .jpg, .jpeg, .webp of .eml.')
      setError('')
      return
    }
"""
if old in text:
    text = text.replace(old, new, 1)
    changes += 1
elif new in text:
    pass
else:
    raise SystemExit("Kon de document/image/.eml typecheck in processReceiptFileImport niet vinden.")

old = """    if (fileKind === 'email') {
      await processEmailImportFile(file)
      return
    }
"""
new = """    if (fileKind === 'email') {
      setStatus('E-mailbestand uit landingzone wordt via reguliere bestandsimport verwerkt.')
      await processReceiptFileImport(file)
      return
    }
"""
if old in text:
    text = text.replace(old, new, 1)
    changes += 1
elif new in text:
    pass
else:
    raise SystemExit("Kon het .eml-blok in processLandingReceiptFile niet vinden.")

old = """        setStatus(`Kassa is geladen met ${visibleReceiptCount} bon${visibleReceiptCount === 1 ? '' : 'nen'}. Er was wel een technische uploadmelding; details zijn alleen voor de admin beschikbaar.`)
"""
new = """        setStatus(`Kassa is geladen met ${visibleReceiptCount} bon${visibleReceiptCount === 1 ? '' : 'nen'}. Er was wel een technische uploadmelding; gebruik Toon technische foutmelding voor details.`)
"""
if old in text:
    text = text.replace(old, new, 1)
    changes += 1
elif new in text:
    pass
else:
    raise SystemExit("Kon de technische upload fallbackmelding niet vinden.")

old = """            {emailRouteError && ['admin','owner'].includes(String(currentUserDisplayRole || '').trim().toLowerCase()) && (technicalUploadError?.detail || String(emailRouteError || '').startsWith('Upload mislukt. De server gaf een technische fout terug.')) ? (
              <div style={{ display: 'grid', gap: '8px' }}>
"""
new = """            {(technicalUploadError?.detail || (emailRouteError && String(emailRouteError || '').startsWith('Upload mislukt. De server gaf een technische fout terug.'))) ? (
              <div style={{ display: 'grid', gap: '8px' }}>
"""
if old in text:
    text = text.replace(old, new, 1)
    changes += 1
elif new in text:
    pass
else:
    raise SystemExit("Kon de technische-foutknop conditie niet vinden.")

path.write_text(text, encoding="utf-8")
print(f"Kassa .eml landingzone route afgedwongen ({changes} wijziging(en)).")
print("Verplicht eindbeeld:")
print("- processLandingReceiptFile: fileKind === 'email' -> processReceiptFileImport(file)")
print("- processReceiptFileImport accepteert .eml")
print("- processEmailImportFile blijft alleen voor de aparte Email inlezen-knop")
