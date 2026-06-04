from __future__ import annotations

from pathlib import Path

path = Path("frontend/src/features/receipts/KassaPage.jsx")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        """    if (!isSupportedReceiptDocumentFile(file) && !isSupportedReceiptImageFile(file)) {
      setEmailRouteError('Dit bestandstype wordt in deze versie nog niet als bonbestand ondersteund. Gebruik .pdf, .zip, .png, .jpg, .jpeg, .webp of .eml.')
      setError('')
      return
    }
""",
        """    if (!isSupportedReceiptDocumentFile(file) && !isSupportedReceiptImageFile(file) && !isSupportedEmailImportFile(file)) {
      setEmailRouteError('Dit bestandstype wordt in deze versie nog niet als bonbestand ondersteund. Gebruik .pdf, .zip, .png, .jpg, .jpeg, .webp of .eml.')
      setError('')
      return
    }
""",
    ),
    (
        """    if (fileKind === 'email') {
      await processEmailImportFile(file)
      return
    }
""",
        """    if (fileKind === 'email') {
      await processReceiptFileImport(file)
      return
    }
""",
    ),
]

changed = 0
for old, new in replacements:
    if old not in text:
        raise SystemExit(f"Patchblok niet gevonden:\n{old}")
    text = text.replace(old, new, 1)
    changed += 1

path.write_text(text, encoding="utf-8")
print(f"Kassa landingzone .eml-uploadroute aangepast ({changed} wijzigingen).")
print("Controle: landingzone .eml gaat nu via /api/receipts/import, niet via /api/receipts/email-import.")
