"""Import refuses unpinned official source and preserves all five sheet cells."""
import hashlib
from pathlib import Path
import zipfile

import pytest
import inhuis_cbs_official_appendix_import as source


def make_workbook(path: Path):
    x = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    work = f'<workbook xmlns="{x}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
    work += ''.join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(source.TABS, 1))
    work += '</sheets></workbook>'
    relations = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    relations += ''.join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(source.TABS) + 1))
    relations += '</Relationships>'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('xl/workbook.xml', work)
        z.writestr('xl/_rels/workbook.xml.rels', relations)
        z.writestr('xl/sharedStrings.xml', f'<sst xmlns="{x}"><si><t>Halfvolle melk</t></si></sst>')
        for i in range(1, len(source.TABS) + 1):
            z.writestr(f'xl/worksheets/sheet{i}.xml',
                       f'<worksheet xmlns="{x}"><sheetData><row r="2"><c r="A2" t="inlineStr"><is><t>011420</t></is></c><c r="B2" t="s"><v>0</v></c></row></sheetData></worksheet>')


def test_all_five_sheets_and_leading_zeroes(tmp_path, monkeypatch):
    path = tmp_path / 'synthetic.xlsx'
    make_workbook(path)
    monkeypatch.setattr(source, "SOURCE_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    data = source.extract(path)
    assert [s["name"] for s in data["sheets"]] == list(source.TABS)
    assert all(s["nonempty_cells"] == 2 for s in data["sheets"])
    assert data["sheets"][1]["rows"][0]["cells"][0]["value"] == "011420"


def test_empty_introduction_is_allowed_but_empty_data_tab_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / 'synthetic.xlsx'
    make_workbook(path)
    with zipfile.ZipFile(path) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    parts['xl/worksheets/sheet1.xml'] = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData/></worksheet>'
    ).encode()
    with zipfile.ZipFile(path, 'w') as z:
        for name, content in parts.items():
            z.writestr(name, content)
    monkeypatch.setattr(source, "SOURCE_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    data = source.extract(path)
    assert data["sheets"][0]["name"] == "Toelichting"
    assert data["sheets"][0]["nonempty_cells"] == 0
    assert all(s["nonempty_cells"] > 0 for s in data["sheets"][1:])

    parts['xl/worksheets/sheet2.xml'] = parts['xl/worksheets/sheet1.xml']
    with zipfile.ZipFile(path, 'w') as z:
        for name, content in parts.items():
            z.writestr(name, content)
    monkeypatch.setattr(source, "SOURCE_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="data tab is empty"):
        source.extract(path)


def test_unverified_workbook_rejected(tmp_path):
    path = tmp_path / 'synthetic.xlsx'
    make_workbook(path)
    with pytest.raises(ValueError, match="SHA-256"):
        source.extract(path)
