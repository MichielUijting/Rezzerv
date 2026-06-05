from __future__ import annotations

from pathlib import Path

BACKEND = Path("backend/app/main.py")
FRONTEND = Path("frontend/src/features/receipts/KassaPage.jsx")
PARSER = Path("backend/app/receipt_ingestion/service_parts/store_specific_parsers.py")


def patch_parser() -> int:
    path = PARSER
    text = path.read_text(encoding="utf-8")
    old = "cleaned = re.sub(r'[]+', '', line).strip()"
    new = "cleaned = re.sub(r'[\\[\\]]+', '', line).strip()"
    if old in text:
        text = text.replace(old, new, 1)
        path.write_text(text, encoding="utf-8")
        return 1
    if new in text:
        return 0
    raise SystemExit("Picnic-regel voor bracket-cleanup niet gevonden in store_specific_parsers.py")


def patch_backend() -> int:
    path = BACKEND
    text = path.read_text(encoding="utf-8")
    route_marker = '@app.post("/api/receipts/picnic-email-import")'
    if route_marker in text:
        return 0

    anchor = '\n\n@app.post("/api/receipts/email-import")\n'
    if anchor not in text:
        raise SystemExit("Anker voor email-import route niet gevonden in backend/app/main.py")

    route = r'''

@app.post("/api/receipts/picnic-email-import")
async def import_picnic_email_receipt(
    household_id: str = Form(...),
    email_file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    """Handmatige Picnic .eml-import via de Kassa-landingzone.

    Deze route is bewust losgekoppeld van /api/receipts/email-import en gebruikt dus
    geen receipt source helper of mailboxconfiguratie. De .eml wordt direct als
    message/rfc822 door de bestaande ingest/picnic-parserketen gehaald.
    """
    context = require_household_context(authorization, household_id)
    effective_household_id = str(context['active_household_id']).strip() or '1'
    email_bytes = await email_file.read()
    if not email_bytes:
        raise HTTPException(status_code=400, detail='Het Picnic e-mailbestand is leeg.')

    source_filename = email_file.filename or 'picnic-receipt.eml'
    if not _looks_like_email_upload(source_filename, email_file.content_type):
        raise HTTPException(status_code=400, detail='Gebruik een opgeslagen .eml-bestand voor Picnic.')

    source_id = f"{effective_household_id}-picnic-eml-upload"
    try:
        payload = parse_email_receipt_payload(email_bytes, fallback_filename=source_filename)
        result = ingest_receipt(
            engine=engine,
            receipt_storage_root=RECEIPT_STORAGE_ROOT,
            household_id=str(effective_household_id),
            filename=source_filename,
            file_bytes=email_bytes,
            source_id=source_id,
            mime_type='message/rfc822',
            reject_non_receipt=False,
            create_failed_receipt_table=True,
            failed_store_name='Picnic',
            failed_purchase_at=payload.get('received_at'),
        )
        raw_receipt_id = result.get('raw_receipt_id')
        if raw_receipt_id:
            store_receipt_email_metadata(raw_receipt_id, str(effective_household_id), payload)
        receipt_table_id = result.get('receipt_table_id')
        if receipt_table_id:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE receipt_tables
                        SET store_name = COALESCE(store_name, 'Picnic'),
                            purchase_at = COALESCE(purchase_at, :purchase_at),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {'id': receipt_table_id, 'purchase_at': payload.get('received_at')},
                )
        result['source_id'] = source_id
        result['source_label'] = 'Handmatige Picnic e-mailupload'
        result['sender_email'] = payload.get('sender_email')
        result['sender_name'] = payload.get('sender_name')
        result['subject'] = payload.get('subject')
        result['received_at'] = payload.get('received_at')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('Onverwachte fout bij handmatige Picnic e-mailimport voor household %s', effective_household_id)
        raise HTTPException(status_code=500, detail='Het Picnic e-mailbestand kon niet volledig als kassabon worden verwerkt.') from exc

    status_code = 200 if result.get('duplicate') else 201
    return JSONResponse(status_code=status_code, content=result)
'''

    text = text.replace(anchor, route + anchor, 1)
    path.write_text(text, encoding="utf-8")
    return 1


def patch_frontend() -> int:
    path = FRONTEND
    text = path.read_text(encoding="utf-8")
    changes = 0

    if "async function uploadPicnicEmailReceiptFile" not in text:
        anchor = "\n\nasync function uploadEmailReceiptFile(householdId, emailFile) {"
        if anchor not in text:
            raise SystemExit("Anker uploadEmailReceiptFile niet gevonden in KassaPage.jsx")
        helper = r'''

async function uploadPicnicEmailReceiptFile(householdId, emailFile) {
  const token = localStorage.getItem('rezzerv_token') || ''
  const formData = new FormData()
  formData.append('household_id', String(householdId))
  formData.append('email_file', emailFile)

  const response = await fetch('/api/receipts/picnic-email-import', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })
  const responseText = await response.text()
  let data = null
  if (responseText) {
    try {
      data = JSON.parse(responseText)
    } catch {
      data = responseText
    }
  }
  if (!response.ok) {
    const error = new Error(normalizeErrorMessage(data?.detail || data || response.statusText))
    error.technicalUploadError = createUploadTechnicalError(response, responseText, '/api/receipts/picnic-email-import')
    throw error
  }
  return data
}
'''
        text = text.replace(anchor, helper + anchor, 1)
        changes += 1

    if "async function processPicnicEmailLandingFile" not in text:
        anchor = "\n\n  async function processEmailImportFile(file) {"
        if anchor not in text:
            raise SystemExit("Anker processEmailImportFile niet gevonden in KassaPage.jsx")
        process = r'''

  async function processPicnicEmailLandingFile(file) {
    if (!file) {
      setEmailRouteError('Sleep een opgeslagen Picnic .eml-bestand naar het landingsgebied.')
      setError('')
      return
    }
    if (!isSupportedEmailImportFile(file)) {
      setEmailRouteError('Gebruik voor Picnic een opgeslagen .eml-bestand.')
      setError('')
      return
    }
    setIsUploading(true)
    setUploadProgressState(true, 'Picnic e-mail voorbereiden...', 'Rezzerv zet de opgeslagen e-mail klaar voor het Picnic-parserframe.', 20)
    setError('')
    setStatus('Picnic e-mailbestand uit landingzone wordt via de aparte Picnic-import verwerkt.')
    setDuplicateNotice('')
    setEmailRouteError('')
    clearTechnicalUploadError()
    try {
      const result = await uploadPicnicEmailReceiptFile(householdId, file)
      const uploadedReceiptId = String(result?.receipt_table_id || '')
      if (result?.duplicate) {
        announceDuplicate(result)
      } else {
        setOpenedReceiptId('')
        setOpenedReceipt(null)
        setFilters(DEFAULT_RECEIPT_FILTERS)
        setReceiptInboxFocusId(uploadedReceiptId)
        setUploadProgressState(true, 'Kassa laden...', buildPostImportProgressMessage('De Picnic e-mailbon'), 85)
        const refreshedItems = await loadReceiptsWithUploadedFallback(result, { openReceiptId: uploadedReceiptId })
        const receiptExistsInInbox = uploadedReceiptId
          ? refreshedItems.some((item) => String(item?.receipt_table_id || '') === uploadedReceiptId)
          : false
        if (uploadedReceiptId && receiptExistsInInbox) {
          setSelectedReceiptIds([uploadedReceiptId])
          await openReceiptDetail(uploadedReceiptId, refreshedItems)
          clearTransientReceiptPreview()
        } else {
          setSelectedReceiptIds([])
        }
        setDuplicateNotice('')
        setStatus(result?.receipt_table_id ? 'Picnic e-mailbon ontvangen. De bon staat nu in de Kassa.' : 'Picnic e-mail verwerkt, maar nog niet als bruikbare kassabon herkend.')
        setUploadProgressState(true, 'Kassa openen...', 'De nieuwe Picnic e-mailbon staat klaar in Kassa.', 100)
        if (isAddReceiptRoute) navigate('/kassa')
      }
    } catch (err) {
      const technical = err?.technicalUploadError || null
      if (technical) setTechnicalUploadError(technical)
      setEmailRouteError(technical?.userMessage || normalizeErrorMessage(err?.message) || 'Picnic e-mailupload is mislukt.')
      setError('')
    } finally {
      setIsUploading(false)
      resetUploadProgress()
      setUploadMode('manual')
    }
  }
'''
        text = text.replace(anchor, process + anchor, 1)
        changes += 1

    old = """    if (fileKind === 'email') {
      await processEmailImportFile(file)
      return
    }
"""
    new = """    if (fileKind === 'email') {
      await processPicnicEmailLandingFile(file)
      return
    }
"""
    if old in text:
        text = text.replace(old, new, 1)
        changes += 1
    elif new in text:
        pass
    else:
        raise SystemExit("Landingzone email-blok niet gevonden in KassaPage.jsx")

    path.write_text(text, encoding="utf-8")
    return changes


def main() -> int:
    parser_changes = patch_parser()
    backend_changes = patch_backend()
    frontend_changes = patch_frontend()
    print("Dedicated Picnic EML import route patch uitgevoerd.")
    print(f"- Picnic regex fix: {parser_changes} wijziging(en)")
    print(f"- Backendroute /api/receipts/picnic-email-import: {backend_changes} wijziging(en)")
    print(f"- Frontend landingzone naar Picnic-route: {frontend_changes} wijziging(en)")
    print("Verplicht testpad: .eml in landingzone -> POST /api/receipts/picnic-email-import")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
