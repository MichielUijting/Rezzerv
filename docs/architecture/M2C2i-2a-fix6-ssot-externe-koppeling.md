# M2C2i-2a-fix6 — Single Source of Truth voor Externe-databases-koppeling

## Architectuurbesluit

De gekoppeld-status van een bonartikel wordt niet op meerdere plaatsen bepaald.

Er is exact één centrale waarheid:

```text
bonartikel -> actieve externe kandidaat -> standaardartikel/cataloguskoppeling
```

Alle presentatieteksten, filters, knoppen en kandidaatregels gebruiken uitsluitend de backendvelden die van deze centrale koppeling zijn afgeleid.

## Functionele invariant

Per bonartikel/context_key geldt:

```text
maximaal één actieve externe koppeling
```

Als een bonartikel gekoppeld is, dan geldt dit op alle UI-niveaus:

- bovenste bonartikeltabel;
- kandidaatdetails onderin;
- filter Gekoppeld/Niet gekoppeld;
- knoppen Koppel artikel/Ontkoppel artikel.

## Backend-contract

De backend levert per kandidaatregel minimaal:

```json
{
  "context_key": "...",
  "active_external_candidate_id": "...",
  "is_linked": true,
  "is_linked_to_catalog": true,
  "is_existing_link_for_receipt_item": true,
  "is_linkable_to_catalog": false,
  "status_label": "Gekoppeld"
}
```

De frontend mag niet zelfstandig opnieuw bepalen of een bonartikel gekoppeld is op basis van:

- `global_product_id`;
- kandidaatstatus-tekst;
- catalogus-id;
- eigen afgeleide regels.

## Niet in scope

- Geen nieuwe OFF-datakwaliteit.
- Geen automatische voorraadmutatie.
- Geen nieuwe Mijn-artikel-mutatie.
- Geen wijziging in Kassa of Uitpakken.
- Geen visuele herstyling.
