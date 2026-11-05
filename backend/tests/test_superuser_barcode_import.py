"""Contract: imported barcode proposals are read-only until one Superuser approves."""
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.api import barcode_import_routes as imports

def _item(**overrides):
    result = {"id": "receipt-table-line:1", "retailer_code": "ah",
              "receipt_line_text": "AH Komkommer", "receipt_article_number": "12345",
              "link_status": "unlinked", "article_code": "", "manual_barcode": ""}
    result.update(overrides)
    return result

def _csv(rows):
    return ("Artikel;Winkelketen;Bonartikelnummer;Art./Barcode;Aanvulstatus;Bron/onderbouwing;Gevonden productnaam\n"
            + "\n".join(rows) + "\n")

def _line(code="8712345678904", status="Aangevuld: officieel artikelnummer"):
    return f"AH Komkommer;Albert Heijn;12345;{code};{status};Winkelpagina;AH Komkommer"

def _superuser(monkeypatch, allowed=True):
    monkeypatch.setattr(imports, "resolve_current_server_session",
                        lambda: SimpleNamespace(is_platform_superuser=allowed))

def _request(gtin="8712345678904"):
    return imports.ApproveRequest(receipt_item_id="receipt-table-line:1",
                                  retailer="Albert Heijn", article="AH Komkommer",
                                  article_number="12345", gtin=gtin)

def test_non_superuser_cannot_preview_or_approve(monkeypatch):
    _superuser(monkeypatch, False)
    with pytest.raises(HTTPException) as err:
        imports.preview_barcode_import(imports.PreviewRequest(csv_text=_csv([_line()])))
    assert err.value.status_code == 403
    with pytest.raises(HTTPException) as err:
        imports.approve_barcode_import(_request())
    assert err.value.status_code == 403

def test_preview_proposes_only_new_rows_never_writes(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles", lambda: {"items": [_item()]})
    monkeypatch.setattr(imports, "save_ed2_manual_barcode",
                        lambda *args: (_ for _ in ()).throw(AssertionError("preview wrote")))
    rows = [_line(), _line(status="Al aanwezig"), _line(code=""),
            "Niet gevonden;Lidl;789;;Niet vastgesteld;;"]
    result = imports.preview_barcode_import(imports.PreviewRequest(csv_text=_csv(rows)))
    assert (result["total"], result["ready"], result["blocked"], result["skipped"]) == (4, 1, 1, 2)
    assert result["items"][0]["receipt_item_id"] == "receipt-table-line:1"

@pytest.mark.parametrize("change", [
    {"article_code": "8712345678904"},
    {"manual_barcode": "8712345678904"},
    {"link_status": "linked"},
])
def test_existing_identity_not_overwritten(monkeypatch, change):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": [_item(**change)]})
    result = imports.preview_barcode_import(imports.PreviewRequest(csv_text=_csv([_line()])))
    assert result["ready"] == 0 and result["blocked"] == 1

def test_approve_rechecks_identity_and_calls_canonical_writer_once(monkeypatch):
    _superuser(monkeypatch)
    index = [_item()]
    monkeypatch.setattr(imports, "list_all_external_articles", lambda: {"items": index})
    applied = []
    monkeypatch.setattr(imports, "save_ed2_manual_barcode", lambda payload:
                        applied.append(payload) or {"saved": True, "source": "manual"})
    assert imports.approve_barcode_import(_request())["saved"]
    assert len(applied) == 1 and applied[0].gtin == "8712345678904"
    index[0]["link_status"] = "linked"
    with pytest.raises(HTTPException) as err:
        imports.approve_barcode_import(_request())
    assert err.value.status_code == 409 and len(applied) == 1

def test_duplicate_source_and_invalid_gtin_blocked(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": [_item(), _item(id="receipt-table-line:2")]})
    result = imports.preview_barcode_import(imports.PreviewRequest(csv_text=_csv([_line()])))
    assert result["ready"] == 0 and result["blocked"] == 1
    with pytest.raises(HTTPException) as err:
        imports.approve_barcode_import(_request("8712345678905"))
    assert err.value.status_code == 422


def test_original_export_gets_actionable_error_without_database_access(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: (_ for _ in ()).throw(AssertionError("original CSV should not query data")))
    original = (
        "Artikel;Winkelketen;Bonartikelnummer;Art./Barcode;GS1-class.;Omvang / gewicht\n"
        "Pindakaas;Jumbo;JUMBO-SEED-3;8718452861309;Classificatie ontbreekt;1 pot\n"
    )
    with pytest.raises(HTTPException) as error:
        imports.preview_barcode_import(imports.PreviewRequest(csv_text=original))
    assert error.value.status_code == 422
    assert "oorspronkelijke exportbestand" in error.value.detail
    assert "artikelen_aangevuld.csv" in error.value.detail


def test_enriched_csv_header_with_all_actual_columns_is_accepted(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": [_item()]})
    csv_text = (
        "Artikel;Winkelketen;Bonartikelnummer;Art./Barcode;GS1-class.;Omvang / gewicht;"
        "Aanvulstatus;Bron/onderbouwing;Gevonden productnaam;Opmerking\n"
        "AH Komkommer;Albert Heijn;12345;8712345678904;Niet gekoppeld;1 stuk;"
        "Aangevuld: officieel artikelnummer;Winkelpagina;AH Komkommer;\n"
    )
    result = imports.preview_barcode_import(imports.PreviewRequest(csv_text=csv_text))
    assert result["total"] == 1
    assert result["ready"] == 1
    assert result["blocked"] == 0
