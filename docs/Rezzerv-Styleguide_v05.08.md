# Rezzerv Styleguide v05.08 (wijziging t.o.v. v05.07)

## Wijziging: knoptekst niet meer vet (globaal)

Vanaf v05.08 geldt:
- Tekst in knoppen is **normaal** (font-weight: 400).
- Dit geldt voor zowel `<button>` als `<a role="button">` (waar van toepassing).

### Reden
De navigatie-UI (Startpagina) werd visueel te zwaar met vetgedrukte knoplabels. Om consistentie te behouden is dit nu **globaal** doorgevoerd.

### Implementatie
- CSS: `.rz-btn { font-weight: 400; }`
- Oude regel uit v05.07 (“knoppen vet”) is hiermee vervangen.

## Ongewijzigd
- Zoekveld placeholdertekst blijft vet (zoals eerder afgesproken).
- Input/select hoogte blijft “natuurlijk” (geen geforceerde hoogte).
- Header logo-regels blijven ongewijzigd.
