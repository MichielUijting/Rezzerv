from pathlib import Path

TARGET = Path("frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: verwacht exact 1 overeenkomst, gevonden {count}")
    return source.replace(old, new, 1)


def main() -> None:
    source = TARGET.read_text(encoding="utf-8-sig")

    source = replace_once(
        source,
        "const selectedCandidateCanBeLinked = Boolean(selectedItem && selectedCandidate && hasValidProductTypeDecision && !isLinkingProductType && !isClassifyingProductType)",
        "const selectedCandidateCanBeLinked = Boolean(selectedItem && selectedCandidate && !isLinkingProductType && !isClassifyingProductType)",
        "koppelpoort",
    )

    source = replace_once(
        source,
        """    const productTypeAssignment = {
      product_type_id: selectedProductTypeId,
      mapping_source: 'external_gs1_gpc',
      confidence_score: 1,
    }""",
        """    const productTypeAssignment = hasValidProductTypeDecision ? {
      product_type_id: selectedProductTypeId,
      mapping_source: 'external_gs1_gpc',
      confidence_score: 1,
    } : null""",
        "optionele Producttypetoewijzing",
    )

    source = replace_once(
        source,
        "          product_type_assignment: productTypeAssignment,",
        "          ...(productTypeAssignment ? { product_type_assignment: productTypeAssignment } : {}),",
        "optionele API-payload",
    )

    source = replace_once(
        source,
        """      const selectedProductType = productTypeOptions.find((option) => option.inventory_group_key === selectedProductTypeId)
      const productTypeLabel = selectedProductType
        ? `${selectedProductType.display_name} — GPC ${selectedProductType.gpc_brick_code}`
        : selectedProductTypeId
      onMessage?.(`Artikel is gekoppeld aan Producttype ${productTypeLabel}.`)""",
        """      if (hasValidProductTypeDecision) {
        const selectedProductType = productTypeOptions.find((option) => option.inventory_group_key === selectedProductTypeId)
        const productTypeLabel = selectedProductType
          ? `${selectedProductType.display_name} — GPC ${selectedProductType.gpc_brick_code}`
          : selectedProductTypeId
        onMessage?.(`Kandidaat is aan het bonartikel gekoppeld met Producttype ${productTypeLabel}.`)
      } else {
        onMessage?.('Kandidaat is aan het bonartikel gekoppeld. Het Producttype moet nog worden vastgesteld.')
      }""",
        "succesmelding",
    )

    source = replace_once(
        source,
        "{isLinkingProductType ? 'Koppelen...' : 'Koppel artikel en Producttype'}",
        "{isLinkingProductType ? 'Koppelen...' : (hasValidProductTypeDecision ? 'Koppel artikel en Producttype' : 'Koppel kandidaat aan bonartikel')}",
        "knoptekst",
    )

    TARGET.write_text(source, encoding="utf-8")
    print("CANDIDATE_LINK_WITHOUT_PRODUCT_TYPE_FIX_APPLIED")


if __name__ == "__main__":
    main()
