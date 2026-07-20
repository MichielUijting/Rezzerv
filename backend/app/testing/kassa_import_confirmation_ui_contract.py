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
        feedback_source.count("fontSize: '18px'") >= 4,
        "melding, toelichting, labels en invoertekst gebruiken minimaal 18px",
    )
    require(
        "fontSize: '22px'" in feedback_source,
        "titel van de centrale melding gebruikt 22px",
    )
    require(
        "minHeight: '48px'" in feedback_source,
        "centrale invoervelden hebben voldoende hoogte",
    )
    require(
        "fontSize: '16px'" in feedback_source,
        "primaire knop heeft grotere knoptekst",
    )
    require(
        "data-testid={`${testId}-field-${field.name}`}\n"
        "                  style={{\n"
        "                    minHeight: '48px',\n"
        "                    padding: '10px 12px',\n"
        "                    fontSize: '18px',"
        in feedback_source,
        "tekst in centrale invoervelden is even groot en niet vet",
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
        "showImportConfirmation = false," in kassa_source,
        "normaal openen van een bestaande bon activeert geen importmelding",
    )
    require(
        "if (showImportConfirmation) {" in kassa_source,
        "de importmelding wordt alleen na een expliciete importaanroep geopend",
    )
    require(
        kassa_source.count(
            "uploadedReceiptId,\n"
            "            refreshedItems,\n"
            "            null,\n"
            "            true,"
        ) == 3,
        "alle drie nieuwe-bonimportpaden activeren de eenmalige controle",
    )
    require(
        kassa_source.count("if (uploadedReceiptId) {") == 3,
        "de importmelding wacht niet op opname in de ververste hoofdtabel",
    )
    require(
        "if (uploadedReceiptId && receiptExistsInInbox) {" not in kassa_source,
        "geen importpad blokkeert de melding op een vertraagde lijstverversing",
    )
    require(
        "onReceiptUpdated={applyReceiptUpdate}" in kassa_source,
        "detail en hoofdtabel gebruiken dezelfde updatefunctie",
    )


if __name__ == "__main__":
    main()
