from app.services import product_web_lookup_service as service


class _FakeResponse:
    status = 200

    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def getcode(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_myrealfood_exact_gtin_extracts_known_product(monkeypatch):
    page = """
    <html>
      <head><title>Producto Curry Madrás - Vitasia</title></head>
      <body></body>
    </html>
    """
    monkeypatch.setattr(
        service.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(page),
    )

    result = service.lookup_myrealfood_product_by_gtin("4056489927952")

    assert result["status"] == "found"
    assert result["gtin"] == "4056489927952"
    assert result["product"]["product_name"] == "Curry Madrás"
    assert result["product"]["brand"] == "Vitasia"
    assert result["product"]["source"] == "myrealfood"
    assert result["product"]["source_url"].endswith("/4056489927952")
    assert result["mutated"] is False


def test_shared_exact_gtin_falls_back_to_myrealfood(monkeypatch):
    monkeypatch.setattr(
        service,
        "lookup_off_product_by_gtin",
        lambda gtin: {
            "ok": True,
            "status": "not_found",
            "gtin": gtin,
            "product": None,
            "mutated": False,
        },
    )
    monkeypatch.setattr(
        service,
        "lookup_myrealfood_product_by_gtin",
        lambda gtin: {
            "ok": True,
            "status": "found",
            "gtin": gtin,
            "product": {
                "gtin": gtin,
                "product_name": "Curry Madrás",
                "brand": "Vitasia",
                "source": "myrealfood",
            },
            "mutated": False,
        },
    )

    result = service.lookup_exact_gtin_sources("4056489927952")

    assert result["status"] == "found"
    assert result["matched_source"] == "myrealfood"
    assert result["product"]["product_name"] == "Curry Madrás"
    assert [item["source"] for item in result["sources"]] == [
        "open_food_facts",
        "myrealfood",
    ]
    assert result["mutated"] is False
