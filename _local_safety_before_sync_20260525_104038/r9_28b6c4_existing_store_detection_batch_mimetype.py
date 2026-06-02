from pathlib import Path

root = Path(r"C:\Users\Gebruiker\Rezzerv_Github")
src = root / "tools/R9-28B6C3_existing_store_detection_batch_resource_safe.py"
dst = root / "tools/R9-28B6C4_existing_store_detection_batch_mimetype.py"

text = src.read_text(encoding="utf-8")

text = text.replace(
    "import json\nimport re\nimport sys\nimport zipfile\n",
    "import json\nimport mimetypes\nimport re\nimport sys\nimport zipfile\n",
)

old = """def _call_existing_parse_receipt_content(data: bytes, filename: str) -> dict[str, Any]:
    svc = importlib.import_module("app.services.receipt_service")
    if not hasattr(svc, "parse_receipt_content"):
        raise RuntimeError("app.services.receipt_service.parse_receipt_content ontbreekt")

    fn = svc.parse_receipt_content
    sig = inspect.signature(fn)

    candidates = [
        ("bytes_filename_kwargs", lambda: fn(data, filename=filename)),
        ("bytes_filename_positional", lambda: fn(data, filename)),
        ("bytes_only", lambda: fn(data)),
        ("content_filename_kwargs", lambda: fn(content=data, filename=filename)),
        ("file_bytes_filename_kwargs", lambda: fn(file_bytes=data, filename=filename)),
        ("raw_bytes_filename_kwargs", lambda: fn(raw_bytes=data, filename=filename)),
    ]

    attempts = []
    last_error = None
    for label, caller in candidates:
        try:
            result = caller()
            return {
                "call_style": label,
                "signature": str(sig),
                "ok": True,
                "result": result,
                "result_jsonable": _jsonable(result),
            }
        except TypeError as exc:
            last_error = f"{label}: {exc}"
            attempts.append({"call_style": label, "error": str(exc)})
            continue
        except Exception as exc:
            return {
                "call_style": label,
                "signature": str(sig),
                "ok": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "attempts": attempts,
            }
    return {
        "call_style": None,
        "signature": str(sig),
        "ok": False,
        "error_type": "NoCompatibleCallStyle",
        "error_message": last_error or "Geen compatible call-style gevonden",
        "attempts": attempts,
    }
"""

new = """def _guess_mime_type(filename: str) -> str:
    guessed = mimetypes.guess_type(filename)[0]
    if guessed:
        return guessed
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix in {".tif", ".tiff"}:
        return "image/tiff"
    return "application/octet-stream"


def _call_existing_parse_receipt_content(data: bytes, filename: str) -> dict[str, Any]:
    svc = importlib.import_module("app.services.receipt_service")
    if not hasattr(svc, "parse_receipt_content"):
        raise RuntimeError("app.services.receipt_service.parse_receipt_content ontbreekt")

    fn = svc.parse_receipt_content
    sig = inspect.signature(fn)
    mime_type = _guess_mime_type(filename)

    candidates = [
        ("bytes_filename_mimetype_positional", lambda: fn(data, filename, mime_type)),
        ("bytes_filename_mimetype_kwargs", lambda: fn(data, filename=filename, mime_type=mime_type)),
        ("file_bytes_filename_mimetype_kwargs", lambda: fn(file_bytes=data, filename=filename, mime_type=mime_type)),
        ("content_filename_mimetype_kwargs", lambda: fn(content=data, filename=filename, mime_type=mime_type)),
        ("raw_bytes_filename_mimetype_kwargs", lambda: fn(raw_bytes=data, filename=filename, mime_type=mime_type)),
    ]

    attempts = []
    last_error = None
    for label, caller in candidates:
        try:
            result = caller()
            return {
                "call_style": label,
                "signature": str(sig),
                "mime_type": mime_type,
                "ok": True,
                "result": result,
                "result_jsonable": _jsonable(result),
            }
        except TypeError as exc:
            last_error = f"{label}: {exc}"
            attempts.append({"call_style": label, "error": str(exc)})
            continue
        except Exception as exc:
            return {
                "call_style": label,
                "signature": str(sig),
                "mime_type": mime_type,
                "ok": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "attempts": attempts,
            }
    return {
        "call_style": None,
        "signature": str(sig),
        "mime_type": mime_type,
        "ok": False,
        "error_type": "NoCompatibleCallStyle",
        "error_message": last_error or "Geen compatible call-style gevonden",
        "attempts": attempts,
    }
"""

if old not in text:
    raise SystemExit("Patchpunt _call_existing_parse_receipt_content niet gevonden in C3-tool.")

text = text.replace(old, new)

text = text.replace("R9-28B6C3", "R9-28B6C4")
text = text.replace("resource-safe existing parser store detection batch", "existing parser store detection batch with MIME type")
text = text.replace("Resource-safe AH-selectie via bestaande winkelherkenning", "AH-selectie via bestaande winkelherkenning met MIME-type")
text = text.replace("R9-28B6C3_existing_store_detection_batch_", "R9-28B6C4_existing_store_detection_batch_")
text = text.replace("/tmp/R9-28B6C3_existing_store_batch", "/tmp/R9-28B6C4_existing_store_batch")

dst.write_text(text, encoding="utf-8")

print("R9-28B6C4 toegepast: bestaande parse_receipt_content wordt nu aangeroepen met mime_type.")
print("Geen nieuwe winkelherkenning; geen bestandsnaamdetectie; geen parser-, OCR-, database-, status-, baseline- of UI-wijzigingen.")
print("Aangepast:")
print("- tools/R9-28B6C4_existing_store_detection_batch_mimetype.py")
