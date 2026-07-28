from pathlib import Path

from app.cli.validate_live_gpc_languages import compare_publications


def _write(path: Path, segment_text: str, include_brick: bool = True) -> None:
    brick = '<brick code="10000001" text="Mosterd" />' if include_brick else ''
    path.write_text(
        f'<schema><segment code="50000000" text="{segment_text}"><family code="50010000" text="Familie"><class code="50010100" text="Klasse">{brick}</class></family></segment></schema>',
        encoding="utf-8",
    )


def test_complete_when_all_codes_exist(tmp_path):
    en = tmp_path / "en.xml"
    nl = tmp_path / "nl.xml"
    _write(en, "Food")
    _write(nl, "Voeding")
    report = compare_publications(en, nl)
    assert report["status"] == "complete"
    assert report["missing_total"] == 0


def test_reports_missing_dutch_code(tmp_path):
    en = tmp_path / "en.xml"
    nl = tmp_path / "nl.xml"
    _write(en, "Food")
    _write(nl, "Voeding", include_brick=False)
    report = compare_publications(en, nl)
    assert report["status"] == "incomplete"
    assert report["missing_total"] == 1
    assert report["missing"][0]["entity_code"] == "10000001"
