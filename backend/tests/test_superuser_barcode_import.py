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

def _line(code="8712345678906", status="Aangevuld: officieel artikelnummer"):
    return f"AH Komkommer;Albert Heijn;12345;{code};{status};Winkelpagina;AH Komkommer"

def _superuser(monkeypatch, allowed=True):
    monkeypatch.setattr(imports, "resolve_current_server_session",
                        lambda: SimpleNamespace(is_platform_superuser=allowed))

def _request(gtin="8712345678906"):
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
    {"article_code": "8712345678906"},
    {"manual_barcode": "8712345678906"},
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
    assert len(applied) == 1 and applied[0].gtin == "8712345678906"
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
        imports.approve_barcode_import(_request("8712345678907"))
    assert err.value.status_code == 422


def test_original_four_column_csv_is_previewed_without_auto_write(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": [_item()]})
    monkeypatch.setattr(imports, "save_ed2_manual_barcode",
                        lambda *args: (_ for _ in ()).throw(AssertionError("preview wrote")))
    csv_text = (
        "Artikel;Winkelketen;Bonartikelnummer;Art./Barcode\n"
        "AH Komkommer;Albert Heijn;12345;8712345678906\n"
        "Ander artikel;Jumbo;345;\n"
    )
    result = imports.preview_barcode_import(imports.PreviewRequest(csv_text=csv_text))
    assert (result["total"], result["ready"], result["blocked"], result["skipped"]) == (2, 1, 0, 1)


def test_derived_receipt_number_is_blocked_in_preview_and_approval(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": [_item(receipt_article_number="84679")]})
    pseudo = "2008467900008"
    csv_text = (
        "Artikel;Winkelketen;Bonartikelnummer;Art./Barcode\n"
        f"AH Komkommer;Albert Heijn;84679;{pseudo}\n"
    )
    result = imports.preview_barcode_import(imports.PreviewRequest(csv_text=csv_text))
    assert (result["ready"], result["blocked"]) == (0, 1)
    assert "Afgeleide code" in result["items"][0]["reason"]
    with pytest.raises(HTTPException) as err:
        imports.approve_barcode_import(imports.ApproveRequest(
            receipt_item_id="receipt-table-line:1", retailer="Albert Heijn",
            article="AH Komkommer", article_number="84679", gtin=pseudo,
        ))
    assert err.value.status_code == 422
    assert "Afgeleide code" in err.value.detail



def test_enriched_csv_header_with_all_actual_columns_is_accepted(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": [_item()]})
    csv_text = (
        "Artikel;Winkelketen;Bonartikelnummer;Art./Barcode;GS1-class.;Omvang / gewicht;"
        "Aanvulstatus;Bron/onderbouwing;Gevonden productnaam;Opmerking\n"
        "AH Komkommer;Albert Heijn;12345;8712345678906;Niet gekoppeld;1 stuk;"
        "Aangevuld: officieel artikelnummer;Winkelpagina;AH Komkommer;\n"
    )
    result = imports.preview_barcode_import(imports.PreviewRequest(csv_text=csv_text))
    assert result["total"] == 1
    assert result["ready"] == 1
    assert result["blocked"] == 0


def test_import_approval_passes_explicit_off_mismatch_choice(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles", lambda: {"items": [_item()]})
    sent = []
    monkeypatch.setattr(imports, "save_ed2_manual_barcode",
                        lambda payload: sent.append(payload) or {"saved": True, "source": "manual"})
    payload = _request()
    payload.allow_off_mismatch = True
    assert imports.approve_barcode_import(payload)["saved"]
    assert len(sent) == 1 and sent[0].allow_off_mismatch is True
    assert sent[0].import_off_product_override is True


def test_off_names_fetch_exact_gtins_without_changing_catalog(monkeypatch):
    _superuser(monkeypatch)
    calls = []
    def lookup(gtin):
        calls.append(gtin)
        return {"status": "found", "product": {
            "product_name": "Bouillon Kip", "brand": "Albert Heijn",
            "quantity": "340 ml", "gtin": gtin,
        }}
    monkeypatch.setattr(imports, "lookup_off_product_by_gtin", lookup)
    monkeypatch.setattr(imports, "save_ed2_manual_barcode",
                        lambda *args: (_ for _ in ()).throw(AssertionError("OFF preview wrote to catalog")))
    response = imports.lookup_barcode_import_off_names(imports.OffNamesRequest(
        gtins=["8712345678906", "8712345678906"]
    ))
    assert response["mutated"] is False
    assert calls == ["8712345678906"]
    assert response["items"] == [{
        "gtin": "8712345678906", "status": "found",
        "product_name": "Bouillon Kip", "brand": "Albert Heijn",
        "quantity": "340 ml",
    }]


def test_off_names_is_superuser_only_and_fails_closed_on_invalid_input(monkeypatch):
    _superuser(monkeypatch, False)
    with pytest.raises(HTTPException) as denied:
        imports.lookup_barcode_import_off_names(imports.OffNamesRequest(gtins=["8712345678906"]))
    assert denied.value.status_code == 403
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "lookup_off_product_by_gtin",
                        lambda *args: (_ for _ in ()).throw(AssertionError("Unexpected lookup")))
    for codes in ([], ["8712345678906"] * 11, ["8712345678907"]):
        with pytest.raises(HTTPException) as invalid:
            imports.lookup_barcode_import_off_names(imports.OffNamesRequest(gtins=codes))
        assert invalid.value.status_code == 422


def test_off_names_report_not_found_and_unavailable_separately(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "lookup_off_product_by_gtin", lambda gtin: {
        "status": "not_found" if gtin == "8712345678906" else "external_source_unavailable",
        "product": None,
    })
    result = imports.lookup_barcode_import_off_names(imports.OffNamesRequest(
        gtins=["8712345678906", "8712345678913"]
    ))
    assert [x["status"] for x in result["items"]] == ["not_found", "unavailable"]
    assert all(not x["product_name"] for x in result["items"])


@pytest.mark.parametrize("existing,status,reason", [
    ({"link_status": "classification_pending", "article_code": "8712345678906",
      "catalog_product_name": "AH Komkommer"}, "al_gekoppeld", "Al gekoppeld"),
    ({"link_status": "unlinked", "manual_barcode": "8712345678906"},
     "al_gekoppeld", "Al gekoppeld"),
    ({"link_status": "linked", "article_code": "", "catalog_product_name": "Generiek"},
     "geblokkeerd", "zonder zichtbare barcode"),
    ({"link_status": "classification_pending", "article_code": "8712345678906",
      "manual_barcode": "8718265525399", "catalog_product_name": "Risotto"},
     "conflict", "Catalogus en handmatige barcode verschillen"),
    ({"link_status": "classification_pending", "article_code": "8718265525399"},
     "conflict", "bestaande barcode wijkt af"),
])
def test_existing_import_identity_explains_exact_match_or_conflict(monkeypatch, existing, status, reason):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": [_item(**existing)]})
    output = imports.preview_barcode_import(imports.PreviewRequest(csv_text=_csv([_line()])))
    assert output["ready"] == 0
    assert output["blocked"] == 1
    entry = output["items"][0]
    assert entry["status"] == status
    assert reason in entry["reason"]
    assert entry["existing_catalog_gtin"] == existing.get("article_code", "")
    assert entry["existing_manual_gtin"] == existing.get("manual_barcode", "")
    assert entry["has_barcode_conflict"] == (status == "conflict")


def _jumbo_item(**overrides):
    result = _item(
        id="receipt-table-line:jumbo-1", retailer_code="jumbo",
        receipt_line_text="JUMBO FUET PLAKJES", receipt_article_number="",
    )
    result.update(overrides)
    return result


def _jumbo_csv(*rows):
    return ("Artikel;Winkelketen;Bonartikelnummer;Art./Barcode\n"
            + "\n".join(rows) + "\n")


def _jumbo_request(article="JUMBO FUET PLAKJES"):
    return imports.ApproveRequest(
        receipt_item_id="receipt-table-line:jumbo-1", retailer="Jumbo",
        article=article, article_number="", gtin="8718452767885",
    )


def test_jumbo_without_article_number_previews_and_approves(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": [_jumbo_item()]})
    writes = []
    monkeypatch.setattr(imports, "save_ed2_manual_barcode",
                        lambda payload: writes.append(payload) or {"saved": True, "source": "manual"})
    output = imports.preview_barcode_import(imports.PreviewRequest(
        csv_text=_jumbo_csv("JUMBO FUET PLAKJES;Jumbo;;8718452767885"),
    ))
    assert (output["total"], output["ready"], output["blocked"]) == (1, 1, 0)
    assert output["items"][0]["receipt_item_id"] == "receipt-table-line:jumbo-1"
    assert output["items"][0]["article_number"] == ""
    assert writes == []  # preview is always read-only
    assert imports.approve_barcode_import(_jumbo_request())["saved"] is True
    assert len(writes) == 1
    assert writes[0].receipt_item_id == "receipt-table-line:jumbo-1"
    assert writes[0].gtin == "8718452767885"


def test_jumbo_numberless_identity_is_rechecked_at_approval(monkeypatch):
    _superuser(monkeypatch)
    rows = [_jumbo_item()]
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": rows})
    monkeypatch.setattr(imports, "save_ed2_manual_barcode",
                        lambda payload: (_ for _ in ()).throw(AssertionError("unexpected write")))
    ready = imports.preview_barcode_import(imports.PreviewRequest(
        csv_text=_jumbo_csv("JUMBO FUET PLAKJES;Jumbo;;8718452767885"),
    ))
    assert ready["ready"] == 1
    rows.append(_jumbo_item(id="receipt-table-line:jumbo-2",
                            receipt_line_text="Jumbo Fuet Plakjes"))
    with pytest.raises(HTTPException) as exc:
        imports.approve_barcode_import(_jumbo_request())
    assert exc.value.status_code == 409


def test_jumbo_numberless_identity_never_claims_numbered_product(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": [_jumbo_item(receipt_article_number="84751")]})
    preview = imports.preview_barcode_import(imports.PreviewRequest(
        csv_text=_jumbo_csv("JUMBO FUET PLAKJES;Jumbo;;8718452767885"),
    ))
    assert (preview["ready"], preview["blocked"]) == (0, 1)
    assert preview["items"][0]["receipt_item_id"] == ""


def test_jumbo_numberless_collision_with_numbered_same_name_is_blocked(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles", lambda: {
        "items": [
            _jumbo_item(),
            _jumbo_item(id="receipt-table-line:jumbo-2", receipt_article_number="154"),
        ],
    })
    preview = imports.preview_barcode_import(imports.PreviewRequest(
        csv_text=_jumbo_csv("JUMBO FUET PLAKJES;Jumbo;;8718452767885"),
    ))
    assert (preview["ready"], preview["blocked"]) == (0, 1)
    assert "niet uniek" in preview["items"][0]["reason"]


def test_jumbo_numberless_double_name_is_not_guessed(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles", lambda: {
        "items": [_jumbo_item(), _jumbo_item(id="receipt-table-line:jumbo-2",
                                              receipt_line_text="Jumbo Fuet Plakjes")],
    })
    preview = imports.preview_barcode_import(imports.PreviewRequest(
        csv_text=_jumbo_csv("JUMBO FUET PLAKJES;Jumbo;;8718452767885"),
    ))
    assert (preview["ready"], preview["blocked"]) == (0, 1)
    assert "niet uniek" in preview["items"][0]["reason"]


def test_jumbo_numberless_still_checks_existing_barcode(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles", lambda: {
        "items": [_jumbo_item(link_status="classification_pending",
                               article_code="8718452767885")],
    })
    preview = imports.preview_barcode_import(imports.PreviewRequest(
        csv_text=_jumbo_csv("JUMBO FUET PLAKJES;Jumbo;;8718452767885"),
    ))
    assert preview["ready"] == 0
    assert preview["items"][0]["status"] == "al_gekoppeld"


def test_jumbo_numberless_csv_duplicate_still_blocked(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": [_jumbo_item()]})
    preview = imports.preview_barcode_import(imports.PreviewRequest(
        csv_text=_jumbo_csv(
            "JUMBO FUET PLAKJES;Jumbo;;8718452767885",
            "JUMBO FUET PLAKJES;Jumbo;;8718452767885",
        ),
    ))
    assert (preview["ready"], preview["blocked"]) == (1, 1)
    assert "Dubbele artikelregel" in preview["items"][1]["reason"]


def test_jumbo_blank_article_name_still_blocked(monkeypatch):
    _superuser(monkeypatch)
    monkeypatch.setattr(imports, "list_all_external_articles",
                        lambda: {"items": [_jumbo_item()]})
    preview = imports.preview_barcode_import(imports.PreviewRequest(
        csv_text=_jumbo_csv(";Jumbo;;8718452767885"),
    ))
    assert (preview["ready"], preview["blocked"]) == (0, 1)
    assert "artikelnaam ontbreekt" in preview["items"][0]["reason"]
