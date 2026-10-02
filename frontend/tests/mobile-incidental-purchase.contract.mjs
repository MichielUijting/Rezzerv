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
assert.doesNotMatch(mobileSource, />Annuleren<\/Button>/)
assert.doesNotMatch(mobileSource, /rz-inline-feedback/)
assert.match(source.slice(desktopStart), />Annuleren<\/Button>/)

assert.match(css, /inhuis-green-wallpaper\.svg/)
assert.match(css, /max-width:\s*640px/)
assert.match(css, /min-height:\s*44px/)
assert.match(css, /font-size:\s*var\(--font-size-ui-body\)/)
assert.match(css, /grid-template-columns:\s*1fr 1fr/)
assert.doesNotMatch(css, /font-size:\s*(12|13|15|17|18|20|22)px/)

assert.match(source, /data-testid="mobile-incidental-purchase-recognized"/)

assert.match(source, /data-testid="mobile-incidental-purchase-manual-toggle"/)

assert.match(source, /data-testid="mobile-incidental-purchase-additional-toggle"/)

assert.match(source, /recognizedBarcodeProduct/)

assert.match(source, />Opnieuw scannen<|\? 'Opnieuw scannen'/)

assert.match(scanner, /width: \{ ideal: 2560 \}/)

assert.match(scanner, /height: \{ ideal: 1440 \}/)

assert.match(scanner, /facingMode: \{ exact: 'environment' \}/)

assert.doesNotMatch(scanner, /advanced\.push\(\{ zoom:/)

console.log('MOBILE_INCIDENTAL_PURCHASE_CONTRACT_GREEN')
