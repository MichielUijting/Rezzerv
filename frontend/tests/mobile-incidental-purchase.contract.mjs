import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('../src/pages/IncidentalPurchasePage.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../src/pages/incidentalPurchaseMobile.css', import.meta.url), 'utf8')
const scanner = readFileSync(new URL('../src/lib/barcodeScanner.js', import.meta.url), 'utf8')

assert.match(source, /useMobileAppViewport/)
assert.match(source, /const isMobileViewport = useMobileAppViewport\(\)/)
assert.match(source, /if \(isMobileViewport\)/)
assert.match(source, /data-testid="mobile-incidental-purchase-page"/)
assert.match(source, /<MobileModuleHeader title="Incidentele aankoop" testId="mobile-incidental-purchase-header" \/>/)
assert.match(source, /data-testid="mobile-incidental-purchase-scan"/)
assert.match(source, /variant="primary"[\s\S]*Barcode scannen/)
assert.match(source, /mobileLocationOptions = locationOptions\.locations\.filter/)
assert.match(source, /sublocationsByLocation\.get\(location\)[\s\S]*length > 0/)
assert.match(source, /dataTestId="mobile-incidental-purchase-location"/)
assert.match(source, /dataTestId="mobile-incidental-purchase-sublocation"/)
assert.match(source, /data-testid="mobile-incidental-purchase-manage-locations"/)
assert.match(source, /navigate\('\/instellingen\/locaties'\)/)
assert.match(source, /testId: 'mobile-incidental-purchase-lookup-feedback'/)
assert.match(source, /testId: 'mobile-incidental-purchase-save-feedback'/)
assert.match(source, /stopPurchaseBarcodeCamera\(false, 'barcode-detected'\)/)
assert.match(source, /className="rz-mobile-incidental-purchase-actions"/)
assert.match(source, />Leegmaken<\/Button>/)
assert.match(source, /data-testid="mobile-incidental-purchase-save"/)

const mobileStart = source.indexOf('if (isMobileViewport)')
const desktopStart = source.indexOf('<AppShell title="Incidentele aankoop toevoegen"')
assert.ok(mobileStart >= 0 && desktopStart > mobileStart)
const mobileSource = source.slice(mobileStart, desktopStart)
assert.match(mobileSource, /handleCancelScanner/)
assert.match(mobileSource, />Annuleren<\/Button>/)
assert.doesNotMatch(mobileSource, /rz-inline-feedback/)
assert.match(source.slice(desktopStart), />Annuleren<\/Button>/)

assert.match(css, /inhuis-green-wallpaper\.svg/)
assert.match(css, /max-width:\s*640px/)
assert.match(css, /min-height:\s*44px/)
assert.match(css, /font-size:\s*var\(--font-size-ui-body\)/)
assert.match(css, /grid-template-columns:\s*1fr 1fr/)
assert.doesNotMatch(css, /font-size:\s*(12|13|15|17|18|20|22)px/)

assert.match(source, /data-testid="mobile-incidental-purchase-recognized"/)


assert.match(source, /data-testid="mobile-incidental-purchase-additional-toggle"/)

assert.match(source, /recognizedBarcodeProduct/)


assert.match(scanner, /width: \{ ideal: 2560 \}/)

assert.match(scanner, /height: \{ ideal: 1440 \}/)
assert.match(scanner, /PROCESSED_FRAME_PIPELINE_START/)
assert.match(scanner, /center-wide-contrast/)
assert.match(scanner, /center-tight-contrast/)
assert.match(scanner, /HybridBinarizer/)
assert.match(scanner, /RGBLuminanceSource/)
assert.match(scanner, /enhanceBarcodeImageData/)
assert.match(scanner, /PROCESSED_FRAME_DECODE_RESULT_FOUND/)

assert.match(scanner, /facingMode: \{ exact: 'environment' \}/)

assert.match(source, /Camera wisselen/)
assert.match(source, /purchaseAvailableCameras\.length < 2/)

assert.doesNotMatch(scanner, /advanced\.push\(\{ zoom:/)

assert.match(source, /autoScannerStartedRef/)

assert.match(source, /startPurchaseBarcodeScanner\(''\)/)

assert.match(source, /data-testid="mobile-incidental-purchase-catalog-step"/)

assert.match(source, /data-testid="mobile-incidental-purchase-check"/)

assert.match(source, />Controleren<\/Button>|'Controleren'/)

assert.match(source, /data-testid="mobile-incidental-purchase-to-inventory"/)

assert.match(source, />Naar voorraad<\/Button>/)

assert.match(source, /data-testid="mobile-incidental-purchase-inventory-product"/)

assert.match(source, /Toegevoegd \/ bijgewerkt in Catalogus\./)

assert.match(source, /Catalogus is al bijgewerkt\. Vul alleen de gegevens voor Voorraad aan\./)

assert.match(source, /catalogImageUrl/)

assert.match(source, /className="rz-mobile-incidental-purchase-product-image"/)

assert.match(source, /article_name: String\(articleName \|\| ''\)\.trim\(\) \|\| null/)

assert.match(source, /handleCancelInventoryStep/)

assert.match(source, /navigate\('\/voorraad'\)/)

const scannerHook = readFileSync(new URL('../src/lib/useBarcodeScanner.js', import.meta.url), 'utf8')
assert.match(scannerHook, /AUTO_CAMERA_SWITCH/)
assert.match(scannerHook, /Inhuis probeert automatisch een andere camera/)
assert.match(scannerHook, /autoCameraAttemptedRef/)
assert.match(scannerHook, /startScannerRef\.current\?\.\(alternative\.deviceId\)/)

console.log('MOBILE_INCIDENTAL_PURCHASE_CONTRACT_GREEN')

assert.match(scannerHook, /scanImageFile/)
assert.match(scannerHook, /decodeFromImageUrl/)
assert.match(scannerHook, /Live camera is niet beschikbaar/)
assert.match(source, /capture="environment"/)
assert.match(source, /mobile-incidental-purchase-photo-scan/)
assert.match(source, /purchaseCameraState\.status === 'error'/)
assert.match(source, /scanPurchaseBarcodeImage/)
assert.match(source, /CatalogArticleThumbnail/)
