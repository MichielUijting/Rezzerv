"""No live accounts/network; protocol identity and transport boundary tests."""
import json
from pathlib import Path
import sys
import unittest
import ast
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.diagnostics.retailer_catalog_live_probe import (
    CatalogError, CatalogProbe, GuestTransport, NoRedirect, jsonld_products, load_samples,
    name_compatible, outcome, run, safe_url,
)


class CatalogTests(unittest.TestCase):
    def test_no_receipt_id_as_webshop_id(self):
        calls = []
        def transport(provider, path, payload=None, **kwargs):
            calls.append((provider, path, payload))
            if "anonymous" in path: return {"access_token": "synthetic-guest"}
            if "search/v2" in path:
                return {"products": [{"hqId": 123, "webshopId": 987, "title": "AH halfvolle melk", "brand": "AH"}]}
            self.assertEqual(payload["variables"], {"id": 987})
            return {"data": {"product": {"id": 987, "title": "AH halfvolle melk", "tradeItem": {"gtin": "4056489846932"}}}}
        result = CatalogProbe(transport).search({"provider": "ah", "sku": "123", "name": "AH halfvolle melk"})
        self.assertEqual(result["status"], "receipt_code_and_catalog_gtin_observed")
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["writes"], 0)

    def test_other_namespace_match_stays_suggestion(self):
        source = {"provider": "ah", "sku": "987", "name": "Halfvolle melk"}
        result = outcome(source, [{"name": "Halfvolle melk", "receipt_codes": ["123"], "gtin": "4056489846932"}])
        self.assertEqual(result["status"], "name_suggestions_only")

    def test_conflicting_gtins_never_selected(self):
        source = {"provider": "lidl", "sku": "123", "name": "Halfvolle melk"}
        rows = [{"name": "Halfvolle melk", "receipt_codes": ["123"], "gtin": x} for x in ("4056489846932", "8718452829408")]
        self.assertEqual(outcome(source, rows)["status"], "conflicting_barcode_evidence")

    def test_invalid_gtin_is_not_accepted(self):
        source = {"provider": "lidl", "sku": "123", "name": "Halfvolle melk"}
        result = outcome(source, [{"name": "Halfvolle melk", "receipt_codes": ["123"], "gtin": "4056489846933"}])
        self.assertEqual(result["status"], "receipt_code_match_no_gtin")

    def test_variant_and_unrelated_fallback_rejected(self):
        self.assertFalse(name_compatible("Halfvolle melk", "Gevulde koek"))
        self.assertFalse(name_compatible("Halfvolle melk", "Volle melk"))
        self.assertFalse(name_compatible("Verse halfvolle melk", "Houdbare halfvolle melk"))
        self.assertFalse(name_compatible("Oude kaas plakken", "Jonge kaas plakken"))
        self.assertFalse(name_compatible("Jong belegen kaas plakken", "Oude kaas plakken"))

    def test_private_label_conflict_is_rejected(self):
        source = {"provider": "ah", "sku": "123", "name": "AH Halfvolle melk"}
        result = outcome(source, [{"name": "Campina Halfvolle melk", "brand": "Campina", "receipt_codes": ["123"], "gtin": "4056489846932"}])
        self.assertEqual(result["status"], "no_compatible_product")

    def test_lidl_erp_number_is_not_receipt_ian(self):
        def transport(provider, path, *args, **kwargs):
            return {"items": [{"gridbox": {"data": {"fullTitle": "Halfvolle melk", "erpNumber": "123", "ians": ["456"]}}}]}
        result = CatalogProbe(transport).search({"provider": "lidl", "sku": "123", "name": "Halfvolle melk"})
        self.assertEqual(result["status"], "name_suggestions_only")

    def test_lidl_jsonld_product_only_and_exact_code(self):
        def transport(provider, path, *args, **kwargs):
            if kwargs.get("html"):
                return '<script type="application/ld+json">'+json.dumps({"@type": "Product", "name": "Halfvolle melk", "gtin13": "4056489846932"})+'</script>'
            self.assertIn("version=2.0", path)
            return {"items": [{"gridbox": {"data": {"fullTitle": "Halfvolle melk", "ians": ["123"], "canonicalUrl": "/p/melk/p987"}}}]}
        self.assertEqual(CatalogProbe(transport).search({"provider": "lidl", "sku": "123", "name": "Halfvolle melk"})["status"], "receipt_code_and_catalog_gtin_observed")

    def test_lidl_fallback_drops_irrelevant_products_without_detail_fetch(self):
        def transport(provider, path, *args, **kwargs):
            self.assertFalse(kwargs.get("html", False))
            return {"items": [{"gridbox": {"data": {"fullTitle": "Gevulde koek", "canonicalUrl": "/p/koek/p123"}}}]}
        result = CatalogProbe(transport).search({"provider": "lidl", "sku": "123", "name": "Halfvolle melk"})
        self.assertEqual(result["status"], "no_compatible_product")
        self.assertEqual(result["rejected"], 2)

    def test_jumbo_name_search_never_claims_receipt_code(self):
        def transport(provider, path, payload=None, **kwargs):
            if kwargs.get("html"): return '<a href="/producten/halfvolle-melk-123PAK">Melk</a>'
            return {"data": {"product": {"sku": "123PAK", "title": "Halfvolle melk", "brand": "Jumbo", "ean": "4056489846932"}}}
        result = CatalogProbe(transport).search({"provider": "jumbo", "sku": "", "name": "Halfvolle melk"})
        self.assertEqual(result["status"], "name_suggestions_only")
        self.assertEqual(result["catalog_products_with_gtin"], 1)

    def test_identity_response_mismatch_fails_closed(self):
        def transport(provider, path, payload=None, **kwargs):
            if "anonymous" in path: return {"access_token": "synthetic"}
            if "search/v2" in path: return {"products": [{"hqId": 123, "webshopId": 987, "title": "Melk"}]}
            return {"data": {"product": {"id": 999, "title": "Melk", "tradeItem": {"gtin": "4056489846932"}}}}
        result = CatalogProbe(transport).search({"provider": "ah", "sku": "123", "name": "Melk"})
        self.assertEqual(result["reason"], "product_identity_response_invalid")

    def test_jumbo_public_page_fallback_preserves_exact_product_sku(self):
        def transport(provider, path, payload=None, **kwargs):
            if path == "/api/graphql": raise CatalogError("http_401")
            if path.startswith("/producten/?"): return '<a href="/producten/halfvolle-melk-123PAK">Melk</a>'
            return '<script type="application/ld+json">{"@type":"Product","sku":"123PAK","name":"Halfvolle melk","gtin13":"4056489846932"}</script>'
        result = CatalogProbe(transport).search({"provider": "jumbo", "sku": "", "name": "Halfvolle melk"})
        self.assertEqual(result["status"], "name_suggestions_only")
        self.assertEqual(result["catalog_products_with_gtin"], 1)

    def test_online_cmd_contains_exact_tested_code(self):
        root = Path(__file__).resolve().parents[2]
        script = (root / "scripts/diagnostics/Inhuis_Winkelproduct_Onlineproef.cmd").read_bytes()
        self.assertNotIn(b"\n", script.replace(b"\r\n", b""))
        content = script.decode("cp1252").replace("\r\n", "\n")
        embedded = content.split("    $pythonCode = @'\n", 1)[1].split("\n'@", 1)[0]
        self.assertEqual(embedded, (root / "scripts/diagnostics/retailer_catalog_live_probe.py").read_text().rstrip())
        ast.parse(embedded)
        self.assertIn("ReadToEndAsync()", content)
        for forbidden in ("reset --hard", "compose up", "compose down", "git.exe switch", "pip install"):
            self.assertNotIn(forbidden, content)

    def test_cross_host_and_mutation_blocked_before_network(self):
        for url in ("https://evil.example/p/123", "http://www.lidl.nl/p/123", "https://www.lidl.nl:444/p/123", "https://u:p@www.lidl.nl/p/123", "//127.0.0.1/p/123"):
            with self.assertRaises(CatalogError): safe_url("lidl", url)
        transport = GuestTransport()
        for provider, path, payload, token in (("jumbo", "/api/graphql", {"query": "mutation AddCart{}"}, ""), ("ah", "/user/login", {}, ""), ("lidl", "/p/123", None, "private")):
            with self.assertRaises(CatalogError): transport(provider, path, payload, token=token)
        self.assertEqual(transport.calls, 0)

    def test_redirect_and_response_budget(self):
        transport = GuestTransport()
        transport.calls = 24
        with self.assertRaises(CatalogError): transport("lidl", "/q/api/search?q=test")
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil.example"))

    def test_export_contains_no_names_codes_tokens_or_urls(self):
        def unavailable(*args, **kwargs): raise CatalogError("http_403")
        result = run([{"provider": "lidl", "name": "PRIVATE_PURCHASE", "sku": "PRIVATE_CODE"}], unavailable)
        encoded = json.dumps(result)
        self.assertNotIn("PRIVATE", encoded)
        self.assertEqual(result["groups"][0]["errors"], {"http_403": 1})
        self.assertEqual(result["writes"], 0)

    def test_jsonld_does_not_borrow_offer_gtin(self):
        html = '<script type="application/ld+json">{"@type":"Product","name":"Melk","offers":{"gtin13":"4056489846932"}}</script>'
        products = jsonld_products(html)
        self.assertEqual(len(products), 1)
        self.assertNotIn("gtin13", products[0])

    def test_load_samples_is_readonly_and_lifecycle_scoped(self):
        class Result:
            def scalar_one(self): return "on"
            def mappings(self): return self
            def all(self): return []
        class Connection:
            dialect = type("Dialect", (), {"name": "postgresql"})()
            def exec_driver_sql(self, sql):
                self.test_sql = sql
                return Result()
            def execute(self, sql):
                query = str(sql)
                for contract in ("rr.household_id=rt.household_id", "rs.household_id=rr.household_id", "rt.deleted_at IS NULL", "rtl.line_role='product'", "n<=2"):
                    assert contract in query
                assert query.strip().startswith("WITH")
                return Result()
        self.assertEqual(load_samples(Connection()), [])


if __name__ == "__main__": unittest.main()
