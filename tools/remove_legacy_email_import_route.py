from __future__ import annotations

from pathlib import Path

BACKEND = Path("backend/app/main.py")
FRONTEND = Path("frontend/src/features/receipts/KassaPage.jsx")


def remove_block(text: str, start: str, end: str, label: str) -> tuple[str, int]:
    start_index = text.find(start)
    if start_index < 0:
        return text, 0
    end_index = text.find(end, start_index + len(start))
    if end_index < 0:
        raise SystemExit(f"Eindanker niet gevonden voor {label}")
    return text[:start_index] + text[end_index:], 1


def patch_backend() -> int:
    path = BACKEND
    text = path.read_text(encoding="utf-8")
    text, changed = remove_block(
        text,
        '\n\n@app.post("/api/receipts/email-import")\n',
        '\n\n@app.post("/api/receipts/source-scan")\n',
        "backend /api/receipts/email-import",
    )
    path.write_text(text, encoding="utf-8")
    return changed


def patch_frontend() -> int:
    path = FRONTEND
    text = path.read_text(encoding="utf-8")
    changes = 0

    # Remove legacy upload helper that calls /api/receipts/email-import.
    text, changed = remove_block(
        text,
        "\nasync function uploadEmailReceiptFile(householdId, emailFile) {\n",
        "\nfunction isSupportedEmailImportFile(file) {\n",
        "frontend uploadEmailReceiptFile",
    )
    if changed:
        text = text.replace("\nfunction isSupportedEmailImportFile(file) {\n", "\nfunction isSupportedEmailImportFile(file) {\n", 1)
    changes += changed

    # Remove hidden email-only input from ReceiptUploadInputs.
    old_signature = "function ReceiptUploadInputs({ fileInputRef, cameraInputRef, emailInputRef, onLandingUploadChange, onCameraCaptureChange, onEmailUploadChange }) {"
    new_signature = "function ReceiptUploadInputs({ fileInputRef, cameraInputRef, onLandingUploadChange, onCameraCaptureChange }) {"
    if old_signature in text:
        text = text.replace(old_signature, new_signature, 1)
        changes += 1

    old_email_input = """      <input
        ref={emailInputRef}
        type="file"
        accept=".eml,message/rfc822"
        style={{ display: 'none' }}
        data-testid="kassa-email-file-input"
        onChange={onEmailUploadChange}
      />
"""
    if old_email_input in text:
        text = text.replace(old_email_input, "", 1)
        changes += 1

    # Remove email input ref and chooser function.
    if "  const emailInputRef = useRef(null)\n" in text:
        text = text.replace("  const emailInputRef = useRef(null)\n", "", 1)
        changes += 1

    text, changed = remove_block(
        text,
        "\n  function handleChooseEmailFromHub() {\n",
        "\n  async function copyEmailRouteToClipboard() {\n",
        "frontend handleChooseEmailFromHub",
    )
    if changed:
        text = text.replace("\n  async function copyEmailRouteToClipboard() {\n", "\n  async function copyEmailRouteToClipboard() {\n", 1)
    changes += changed

    # Remove legacy processEmailImportFile.
    text, changed = remove_block(
        text,
        "\n  async function processEmailImportFile(file) {\n",
        "\n  async function processReceiptFileImport(file) {\n",
        "frontend processEmailImportFile",
    )
    if changed:
        text = text.replace("\n  async function processReceiptFileImport(file) {\n", "\n  async function processReceiptFileImport(file) {\n", 1)
    changes += changed

    # Ensure landingzone .eml does not call the removed legacy flow.
    old_landing = """    if (fileKind === 'email') {
      await processEmailImportFile(file)
      return
    }
"""
    new_landing = """    if (fileKind === 'email') {
      await processPicnicEmailLandingFile(file)
      return
    }
"""
    if old_landing in text:
        if "processPicnicEmailLandingFile" not in text:
            raise SystemExit("Dedicated Picnic landingflow ontbreekt. Voer eerst patch_dedicated_picnic_eml_import_route.py uit.")
        text = text.replace(old_landing, new_landing, 1)
        changes += 1

    # Remove legacy direct email upload handler.
    text, changed = remove_block(
        text,
        "\n  async function handleEmailUploadChange(event) {\n",
        "\n  async function handleDroppedLandingFile(file) {\n",
        "frontend handleEmailUploadChange",
    )
    if changed:
        text = text.replace("\n  async function handleDroppedLandingFile(file) {\n", "\n  async function handleDroppedLandingFile(file) {\n", 1)
    changes += changed

    # Remove props and Email button from upload inputs / source hub.
    text = text.replace("\n        emailInputRef={emailInputRef}", "")
    text = text.replace("\n        onEmailUploadChange={handleEmailUploadChange}", "")
    text = text.replace("\n            onChooseEmail={handleChooseEmailFromHub}", "")
    text = text.replace("\n                onChooseEmail={handleChooseEmailFromHub}", "")
    text = text.replace("\n  onChooseEmail,", "")

    old_button_grid = """            <div style={{ display: 'grid', gap: '10px', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', alignItems: 'stretch' }}>
              <Button type="button" variant="primary" onClick={onChooseReceiptFile} disabled={isUploading} data-testid="kassa-choose-file-button" style={{ width: '100%', fontSize: '14px', padding: '10px 12px', whiteSpace: 'nowrap' }}>Bestanden kiezen</Button>
              <Button type="button" variant="secondary" onClick={onChooseCamera} disabled={isUploading} data-testid="kassa-open-camera-button" style={{ width: '100%', fontSize: '14px', padding: '10px 12px', whiteSpace: 'nowrap' }}>Camera openen</Button>
              <Button type="button" variant="secondary" onClick={onChooseEmail} disabled={isUploading} data-testid="kassa-open-email-button" style={{ width: '100%', fontSize: '14px', padding: '10px 12px', whiteSpace: 'nowrap' }}>Email inlezen</Button>
            </div>
"""
    new_button_grid = """            <div style={{ display: 'grid', gap: '10px', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', alignItems: 'stretch' }}>
              <Button type="button" variant="primary" onClick={onChooseReceiptFile} disabled={isUploading} data-testid="kassa-choose-file-button" style={{ width: '100%', fontSize: '14px', padding: '10px 12px', whiteSpace: 'nowrap' }}>Bestanden kiezen</Button>
              <Button type="button" variant="secondary" onClick={onChooseCamera} disabled={isUploading} data-testid="kassa-open-camera-button" style={{ width: '100%', fontSize: '14px', padding: '10px 12px', whiteSpace: 'nowrap' }}>Camera openen</Button>
            </div>
"""
    if old_button_grid in text:
        text = text.replace(old_button_grid, new_button_grid, 1)
        changes += 1

    # Update explanatory copy so it no longer claims .eml uses the legacy route.
    text = text.replace("<div><strong>.eml</strong> blijft via de bestaande e-mailimport lopen.</div>", "<div><strong>.eml</strong> loopt in deze build alleen via de dedicated Picnic-import in de landingsplaats.</div>")

    if "/api/receipts/email-import" in text or "processEmailImportFile" in text or "uploadEmailReceiptFile" in text:
        raise SystemExit("Legacy email-import verwijzingen staan nog in KassaPage.jsx")

    path.write_text(text, encoding="utf-8")
    return changes


def main() -> int:
    backend_changes = patch_backend()
    frontend_changes = patch_frontend()
    print("Legacy EML-importroute verwijderd uit actieve applicatieflow.")
    print(f"- Backend /api/receipts/email-import verwijderd: {backend_changes} wijziging(en)")
    print(f"- Frontend legacy EML-flow verwijderd/aangepast: {frontend_changes} wijziging(en)")
    print("Verplicht eindbeeld:")
    print("- geen /api/receipts/email-import in frontend of backend")
    print("- geen knop Email inlezen")
    print("- .eml in landingzone -> processPicnicEmailLandingFile -> /api/receipts/picnic-email-import")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
