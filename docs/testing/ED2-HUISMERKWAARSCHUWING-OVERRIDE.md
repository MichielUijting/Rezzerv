# ED2: handmatige override van smalle huismerkwaarschuwing

**TEST_LEVEL_PROVISIONAL: L** — autorisatie, centrale productidentiteit en product-/bonkoppeling.

## Scenario

AH CRACKERS en OFF-kandidaat `Mini crackers nature (Lu)`: de bontekst herkent een AH-huismerkmarker, maar de kandidaatspecifieke merknaam is anders. Dit is een **waarschuwing**, geen onherroepelijke blokkade. In zowel **Zelf zoeken in OFF** als de automatische ED2-kandidatenlijst toont de gedeelde ondoorzichtige Melding-overlay eerst **Annuleren** of **Toch koppelen**. Er wordt vóór de bewuste bevestiging niets opgeslagen.

De client moet een server-uitgegeven, receipt- en GTIN-gebonden kortlevend OFF-bewijs meesturen. Uitsluitend de gebruiker met bestaande `platform.external_products.link_existing`-bevoegdheid mag via dezelfde route expliciet `override_private_label_conflict: true` aanvragen. De server berekent de merkwaarschuwing opnieuw uit de originele bron en het ondertekende OFF-product. Een boolean true voor een ander conflict zonder echte huismerkmarker wordt geweigerd. Onjuiste/ontbrekende/verlopen proof, ongeldige GTIN, conflicterende productidentiteit of onvolledige verplichte GS1-authority wordt **niet** overruled.

Een bevestigde override wordt in `external_article_product_links.confirmed_by` gemarkeerd met `*_brand_override`; een voorlopige ontbrekende GS1-classificatie behoudt ook dit specifieke auditmerk. De centrale ED2 read-projectie mag deze expliciet gemarkeerde merkuitzondering niet opnieuw verbergen, maar een loutere GTIN-fallback of gewone niet-overruled mismatch blijft gesloten. Klassificatie, OFF-bewijs en gebruikersvoorraad worden niet gefingeerd of herschreven.

## Acceptatie

- Annuleren verstuurt geen koppeling; Toch koppelen verzendt na bewuste beslissing precies één `override_private_label_conflict: true`.
- Alleen het huismerk-heuristiekconflict is overridebaar, nooit andere beveiligings- of productidentiteitscontroles.
- Beide ED2-kandidaatroutes, desktop en mobiel, tonen dezelfde centrale `Melding`-overlay.
- Bestaande barcode-, hoofd-ED2-teller-, Catalogus-, autorisatie- en OFF-/GPC-regressiecontracten blijven gelden.
- Geen inventaris-/bon-/huishoudmutatie op een platformbrede productkoppeling.
- De grotere PO-besloten CBS-omslag uit #640 blijft apart: deze gerichte PR wijzigt GS1/Shopify-domeinlogica niet.

### Risico

Bestaande handmatig ingevoerde barcodes zonder bevestigd OFF-product krijgen **geen** generieke bypass. Deze PR maakt geen universele 'force koppelen'-route.
