from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


def main() -> None:
    app_root = Path(__file__).resolve().parents[2]
    repository_root = app_root.parent

    feedback_path = (
        repository_root
        / "frontend"
        / "src"
        / "ui"
        / "AppFeedbackProvider.jsx"
    )
    kassa_path = (
        repository_root
        / "frontend"
        / "src"
        / "features"
        / "receipts"
        / "KassaPage.jsx"
    )

    feedback_source = feedback_path.read_text(encoding="utf-8")
    kassa_source = kassa_path.read_text(encoding="utf-8")

    require(
        feedback_path.exists(),
        f"centraal meldingencomponent gevonden op {feedback_path}",
    )
    require(
        kassa_path.exists(),
        f"KassaPage gevonden op {kassa_path}",
    )
    require(
        "inputFields: Array.isArray(input.inputFields)" in feedback_source,
        "centraal meldingencomponent ondersteunt invoervelden",
    )
    require(
        "feedback.onPrimaryAction?.({ ...fieldValues })" in feedback_source,
        "centrale opslagactie ontvangt de ingevoerde waarden",
    )
    require(
        "field.required && !String(fieldValues[field.name] || '').trim()"
        in feedback_source,
        "verplichte centrale invoervelden worden gevalideerd",
    )
    require(
        "function openReceiptImportConfirmation(receipt)" in kassa_source,
        "Kassa bevat één centrale importcontrolefunctie",
    )
    require(
        "store_name_source || '') === 'user_required'" in kassa_source,
        "niet-herkende winkel opent gebruikersinvoer",
    )
    require(
        "purchase_at_source || '') === 'import_default'" in kassa_source,
        "inleesdatumfallback opent datumcontrole",
    )
    require(
        "label: 'Winkel(keten)'" in kassa_source,
        "winkelnaam wordt via de centrale melding gevraagd",
    )
    require(
        "label: 'Aankoopdatum'" in kassa_source,
        "aankoopdatum wordt via de centrale melding getoond",
    )
    require(
        "openReceiptImportConfirmation(importedDetail)" in kassa_source,
        "nieuwe bonimport opent de controle na het laden van de bon",
    )
    require(
        "onReceiptUpdated={applyReceiptUpdate}" in kassa_source,
        "detail en hoofdtabel gebruiken dezelfde updatefunctie",
    )


if __name__ == "__main__":
    main()
