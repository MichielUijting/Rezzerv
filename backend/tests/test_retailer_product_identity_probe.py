"""Synthetic source-boundary tests. No accounts, network or database needed."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import ast
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.diagnostics.retailer_product_identity_probe import (
    audit, line_evidence, read_envelope, source_lines, valid_gtin,
)


class Result:
    def __init__(self, rows=(), scalar=None):
        self.rows, self.scalar = rows, scalar
    def scalar_one(self): return self.scalar
    def mappings(self): return self
    def all(self): return self.rows


class Connection:
    dialect = type("Dialect", (), {"name": "postgresql"})()
    def __init__(self, rows=(), saved=(), read_only="on"):
        self.rows, self.saved, self.read_only, self.queries = rows, saved, read_only, []
    def exec_driver_sql(self, query):
        assert query == "SHOW transaction_read_only"
        return Result(scalar=self.read_only)
    def execute(self, query, params):
        query = str(query).strip()
        assert query.startswith("SELECT")
        self.queries.append((query, params))
        return Result(self.saved if "SELECT rtl.barcode" in query else self.rows)


class IdentityProbeTests(unittest.TestCase):
    def test_windows_script_contains_exact_reviewed_probe(self):
        root = Path(__file__).resolve().parents[2]
        script = (root / "scripts/diagnostics/Inhuis_Winkelproduct_Bronproef.cmd").read_bytes()
        self.assertNotIn(b"\n", script.replace(b"\r\n", b""))
        content = script.decode("cp1252").replace("\r\n", "\n")
        embedded = content.split("    $pythonCode = @'\n", 1)[1].split("\n'@", 1)[0]
        original = (root / "scripts/diagnostics/retailer_product_identity_probe.py").read_text().rstrip()
        self.assertEqual(embedded, original)
        ast.parse(embedded)
        self.assertIn("ReadToEndAsync()", content)
        self.assertIn("WaitForExit(180000)", content)
        self.assertIn("pause", content)
        for forbidden in ("reset --hard", "git.exe switch", "compose up", "compose down", "start.bat", "pip install"):
            self.assertNotIn(forbidden, content)

    def test_gtin_strict_format_and_check_digit(self):
        for value in ("8718452829408", "4056489846932", "00012345600012"):
            self.assertTrue(valid_gtin(value), value)
        for value in ("8718452829409", "00000000", "x8718452829408", " 8718452829408", 8718452829408, True, "８７１８４５２８２９４０８"):
            self.assertFalse(valid_gtin(value), value)

    def test_lidl_scanner_code_is_not_verified_barcode(self):
        row = line_evidence("lidl", {"codeInput": "4056489846932", "articleId": "12345"})
        self.assertEqual(row["status"], "scanner_code_needs_confirmation")
        self.assertTrue(row["scanner_codes"][0]["check_digit_valid"])
        self.assertFalse(row["barcode_link_verified"])

    def test_ah_and_picnic_ids_stay_retailer_ids(self):
        for provider in ("ah", "picnic"):
            row = line_evidence(provider, {"id": "8718452829408"})
            self.assertEqual(row["status"], "retailer_sku_only")
            self.assertEqual(row["explicit_gtins"], [])

    def test_nested_id_never_becomes_gtin(self):
        row = line_evidence("jumbo", {"product": {"id": "8718452829408"}})
        self.assertEqual(row["status"], "retailer_sku_only")

    def test_conflicting_explicit_gtins_fail_closed(self):
        row = line_evidence("ah", {"ean": "4056489846932", "product": {"gtin": "8718452829408"}})
        self.assertEqual(row["status"], "conflicting_gtins")

    def test_invalid_explicit_does_not_disappear_behind_valid(self):
        row = line_evidence("aldi", {"ean": "4056489846932", "barcode": "broken"})
        self.assertEqual(row["status"], "invalid_explicit_gtin")

    def test_numeric_barcode_not_reconstructed(self):
        row = line_evidence("lidl", {"ean": 4056489846932})
        self.assertEqual(row["numeric_identifier_fields"], 1)
        self.assertEqual(row["status"], "invalid_explicit_gtin")

    def test_no_arbitrary_metadata_or_credentials_in_evidence(self):
        row = line_evidence("picnic", {"name": "PRIVATE_NAME", "token": "PRIVATE_TOKEN", "id": "test-sku"})
        self.assertNotIn("PRIVATE", json.dumps(row))

    def test_known_envelope_and_unknown_versions(self):
        self.assertEqual(source_lines({"schema_version": "1.0", "provider": "lidl", "receipt": {"items": []}}), ("lidl", []))
        for payload in ({}, {"schema_version": "2.0"}, {"schema_version": "1.0", "provider": "ah", "receipt": {}}):
            with self.assertRaises(ValueError): source_lines(payload)

    def test_source_hash_and_path_boundaries(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "raw"
            root.mkdir()
            data = b'{"schema_version":"1.0"}'
            path = root / "source.json"
            path.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            self.assertEqual(read_envelope(path, root, digest)["schema_version"], "1.0")
            with self.assertRaises(ValueError): read_envelope(path, root, "wrong")
            outside = Path(directory) / "outside.json"
            outside.write_bytes(data)
            with self.assertRaises(ValueError): read_envelope(outside, root, digest)
            (root / "link.json").symlink_to(outside)
            with self.assertRaises(ValueError): read_envelope(root / "link.json", root, digest)

    def test_audit_requires_readonly_and_reports_absence_honestly(self):
        with self.assertRaises(ValueError): audit(Connection(read_only="off"), "/unused")
        result = audit(Connection(), "/unused")
        self.assertEqual(len(result["providers_without_sources"]), 5)
        self.assertEqual(result["network_requests"], 0)
        self.assertFalse(result["barcode_link_verified"])

    def test_audit_aggregate_privacy_and_household_scoping(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "private-filename.json"
            data = json.dumps({"schema_version": "1.0", "provider": "lidl", "receipt": {"token": "PRIVATE_SECRET", "items": [
                {"name": "PRIVATE_PRODUCT", "ean": "4056489846932"},
                {"name": "PRIVATE_DEPOSIT", "lineType": "deposit"},
                {"codeInput": "12345"},
            ]}}).encode()
            path.write_bytes(data)
            rows = [{"id": "private-receipt", "household_id": "private-household", "provider": "lidl", "storage_path": str(path), "sha256_hash": hashlib.sha256(data).hexdigest()}]
            conn = Connection(rows, [{"barcode": "12345", "external_article_code": "12345"}])
            result = audit(conn, directory)
            group = result["groups"][0]
            self.assertEqual(group["source_lines"], 2)
            self.assertEqual(group["explicit_nonproduct_lines_skipped"], 1)
            self.assertEqual(group["barcode_also_sku"], 1)
            self.assertEqual(group["persisted_valid_gtin_shape"], 0)
            output = json.dumps(result)
            for private in ("PRIVATE", "private-", "4056489846932", "12345", str(path)):
                self.assertNotIn(private, output)
            self.assertIn("rs.household_id=rr.household_id", conn.queries[0][0])
            self.assertEqual(conn.queries[1][1]["household"], "private-household")

    def test_provider_mismatch_and_missing_file_are_counted_not_printed(self):
        row = {"id": "x", "household_id": "h", "provider": "ah", "storage_path": "/missing", "sha256_hash": "0" * 64}
        result = audit(Connection([row]), "/raw")
        self.assertEqual(result["groups"][0]["source_errors"], 1)


if __name__ == "__main__":
    unittest.main()
