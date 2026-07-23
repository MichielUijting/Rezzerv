from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


def main() -> None:
    main_path = Path(__file__).resolve().parents[1] / "main.py"
    source = main_path.read_text(encoding="utf-8")

    require(main_path.exists(), f"main.py gevonden op {main_path}")
    require(
        "'store_name_source': \"TEXT NOT NULL DEFAULT 'detected'\"" in source,
        "receipt_tables bewaart de herkomst van de winkel",
    )
    require(
        "'purchase_at_source': \"TEXT NOT NULL DEFAULT 'detected'\"" in source,
        "receipt_tables bewaart de herkomst van de aankoopdatum",
    )
    require(
        "purchase_at_source = 'import_default'" in source,
        "een niet-herkende aankoopdatum wordt als importfallback gemarkeerd",
    )
    require(
        "'user_required'" in source,
        "een niet-herkende winkel wordt als gebruikersinvoer gemarkeerd",
    )
    require(
        "values['store_name_source'] = 'user'" in source,
        "handmatige winkelinvoer wordt als gebruikerswaarde gemarkeerd",
    )
    require(
        "values['purchase_at_source'] = 'user'" in source,
        "bevestigde of gewijzigde aankoopdatum wordt als gebruikerswaarde gemarkeerd",
    )
    require(
        source.count("rt.store_name_source") >= 2,
        "winkelherkomst staat in Kassa-lijst en bon-detail",
    )
    require(
        source.count("rt.purchase_at_source") >= 2,
        "datumherkomst staat in Kassa-lijst en bon-detail",
    )


if __name__ == "__main__":
    main()
