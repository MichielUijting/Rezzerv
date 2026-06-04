from __future__ import annotations

from pathlib import Path

path = Path("backend/app/main.py")
text = path.read_text(encoding="utf-8")

old_signature = """def import_email_receipt_payload(household_id: str, email_bytes: bytes, fallback_filename: str = 'receipt.eml', source_id: str | None = None) -> dict[str, Any]:
    default_email_source = ensure_household_email_source(household_id)
    payload = parse_email_receipt_payload(email_bytes, fallback_filename=fallback_filename)
    effective_source_id = str(source_id or default_email_source['id']).strip() or default_email_source['id']
"""
new_signature = """def import_email_receipt_payload(
    household_id: str,
    email_bytes: bytes,
    fallback_filename: str = 'receipt.eml',
    source_id: str | None = None,
    require_configured_source: bool = True,
) -> dict[str, Any]:
    default_email_source = None
    if require_configured_source:
        default_email_source = ensure_household_email_source(household_id)
    payload = parse_email_receipt_payload(email_bytes, fallback_filename=fallback_filename)
    fallback_source_id = f"manual-eml-{household_id}"
    effective_source_id = str(source_id or ((default_email_source or {}).get('id')) or fallback_source_id).strip() or fallback_source_id
"""

if old_signature not in text:
    raise SystemExit("Functieheader import_email_receipt_payload niet gevonden; patch niet uitgevoerd.")
text = text.replace(old_signature, new_signature, 1)

old_call = """        result = import_email_receipt_payload(
            household_id=str(household_id),
            email_bytes=file_bytes,
            fallback_filename=filename or 'receipt.eml',
            source_id=source_id,
        )
"""
new_call = """        result = import_email_receipt_payload(
            household_id=str(household_id),
            email_bytes=file_bytes,
            fallback_filename=filename or 'receipt.eml',
            source_id=source_id,
            require_configured_source=False,
        )
"""

if old_call not in text:
    raise SystemExit("Handmatige .eml-call in import_uploaded_receipt_payload niet gevonden; patch niet uitgevoerd.")
text = text.replace(old_call, new_call, 1)

old_label = """    result['source_label'] = default_email_source.get('label', 'E-mail')
"""
new_label = """    result['source_label'] = (default_email_source or {}).get('label', 'Handmatige e-mailupload')
"""

if old_label not in text:
    raise SystemExit("source_label-regel niet gevonden; patch niet uitgevoerd.")
text = text.replace(old_label, new_label, 1)

path.write_text(text, encoding="utf-8")
print("Handmatige .eml-import losgekoppeld van receipt source helper.")
print("/api/receipts/import kan .eml nu verwerken zonder ensure_household_email_source().")
print("/api/receipts/email-import blijft de helperconfiguratie vereisen.")
