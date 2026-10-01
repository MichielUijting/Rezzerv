from pathlib import Path


def test_barcode_save_casts_nullable_parameter_for_postgresql():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")

    assert (
        "external_source = CASE WHEN CAST(:barcode AS TEXT) IS NULL "
        "THEN external_source ELSE COALESCE(external_source, 'manual') END"
        in source
    ), "PostgreSQL moet het datatype van :barcode expliciet kunnen afleiden in de CASE-expressie"
