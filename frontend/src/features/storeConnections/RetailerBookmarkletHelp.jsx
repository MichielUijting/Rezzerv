import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import Button from '../../ui/Button'
import { detectMobileRetailerEnvironment } from './retailerMobileEnvironment.js'

/**
 * Does not silently install scripts, read retailer cookies or treat navigation
 * as a connection. The explicit retailer-side bookmarklet still performs the
 * actual import; server acknowledgements remain the only success proof.
 */
export default function RetailerBookmarkletHelp({
  provider, retailer, open, onClose, bookmarklet, valid = true,
  instructions, onOpenStore, onSkip,
}) {
  const dialogRef = useRef(null)
  const manualRef = useRef(null)
  const [copied, setCopied] = useState(false)
  const [manualCopy, setManualCopy] = useState(false)
  const environment = detectMobileRetailerEnvironment()
  const mobile = environment.device !== 'desktop'
  const supported = environment.browser === 'safari' || environment.browser === 'chrome'

  useEffect(() => {
    if (!open) return undefined
    const previousFocus = document.activeElement
    const dialog = dialogRef.current
    dialog?.querySelector('[data-testid="' + provider + '-help-ok"]')?.focus()
    const keepDialogOpen = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); return }
      if (event.key !== 'Tab' || !dialog) return
      const interactive = [...dialog.querySelectorAll('a[href], button:not([disabled]), textarea')]
      if (!interactive.length) { event.preventDefault(); return }
      const first = interactive[0]
      const last = interactive[interactive.length - 1]
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault(); last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault(); first.focus()
      }
    }
    document.addEventListener('keydown', keepDialogOpen, true)
    return () => {
      document.removeEventListener('keydown', keepDialogOpen, true)
      previousFocus?.focus?.()
    }
  }, [open, provider])
  useEffect(() => {
    if (!open) { setCopied(false); setManualCopy(false) }
  }, [open, bookmarklet])

  async function copyScript() {
    if (!valid || !bookmarklet) return
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable')
      await navigator.clipboard.writeText(bookmarklet)
      setCopied(true)
      setManualCopy(false)
    } catch {
      // Local HTTP/Tailscale can lack Clipboard API. Never claim success.
      setCopied(false)
      setManualCopy(true)
      requestAnimationFrame(() => { manualRef.current?.focus(); manualRef.current?.select() })
    }
  }

  if (!open) return null
  const titleId = provider + '-bookmarklet-help-title'
  const linkTestId = provider === 'jumbo' ? 'jumbo-poc-bookmarklet' : 'lidl-web-bookmarklet'
  const savedName = 'Inhuis ' + retailer + '-bonnen'
  return createPortal(
    <div data-testid={provider + '-bookmarklet-help'} className="rz-retailer-help-backdrop">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId}
        data-testid={provider + '-bookmarklet-dialog'} className="rz-retailer-help-dialog">
        <h3 id={titleId} style={{ margin: 0 }}>
          {mobile ? 'Koppel ' + retailer : 'Eerste keer koppelen met ' + retailer + '?'}
        </h3>
        {mobile ? (
          <section className="rz-retailer-mobile-setup" data-testid={provider + '-mobile-setup'}
            data-device={environment.device} data-browser={environment.browser}>
            <p style={{ margin: 0 }}>Haal je digitale kassabonnen op. Inhuis gebruikt hiervoor eenmalig
              een opgeslagen browserscript, dat je op de website van {retailer} uitvoert.</p>
            {!supported ? <p role="alert" data-testid={provider + '-browser-warning'}>
              Gebruik {environment.device === 'iphone' ? 'Safari op je iPhone' : 'Chrome op je Android-telefoon'}.
              Open Inhuis en de winkel in diezelfde browser; ingebouwde appbrowsers worden niet ondersteund.
            </p> : null}
            <div className="rz-retailer-mobile-step">
              <strong>Stap 1 van 3 · Bereid het script voor</strong>
              <p>Kopieer het script. Maak in {environment.device === 'iphone' ? 'Safari' : 'Chrome'} een bladwijzer
                met de naam <strong>{savedName}</strong> en vervang het webadres door het script.</p>
              <Button type="button" disabled={!valid} onClick={copyScript}
                data-testid={provider + '-mobile-copy'}>{copied ? 'Script gekopieerd' : 'Kopieer script'}</Button>
              {manualCopy ? <div data-testid={provider + '-manual-copy'}>
                <p>Kopiëren is door je browser geblokkeerd. Selecteer de volledige tekst en kopieer handmatig.</p>
                <textarea ref={manualRef} readOnly rows={3} value={bookmarklet}
                  aria-label={retailer + '-script handmatig kopiëren'}
                  onFocus={event => event.currentTarget.select()} />
              </div> : null}
              {environment.device === 'iphone'
                ? <small>Safari: voeg een bladwijzer toe via Delen; ga vervolgens naar Bladwijzers → Wijzig en vervang het adres.</small>
                : <small>Chrome: open Bladwijzers, wijzig het adres van de bewaarde bladwijzer en sla op.</small>}
            </div>
            <div className="rz-retailer-mobile-step">
              <strong>Stap 2 van 3 · Meld je aan</strong>
              <p>Open Mijn {retailer} in dezelfde browser en meld je aan bij de winkel.</p>
              <Button type="button" disabled={!valid || !supported} onClick={onOpenStore}
                data-testid={provider + '-mobile-open-store'}>Open Mijn {retailer}</Button>
            </div>
            <div className="rz-retailer-mobile-step">
              <strong>Stap 3 van 3 · Bonnen ophalen</strong>
              <p>{environment.device === 'iphone'
                ? 'Open op de winkelwebsite je bladwijzers en tik op ' + savedName + '.'
                : 'Typ op de winkelwebsite de bladwijzernaam in de adresbalk en kies de opgeslagen bladwijzer.'}
                {' '}Het script haalt de bonnen op en stuurt het resultaat terug naar Inhuis.
                Houd bij Lidl het Inhuis-tabblad geopend.</p>
              <small>Een geopende website is geen geslaagde koppeling. Inhuis wacht op bevestigde bonontvangst.</small>
            </div>
            <div className="rz-retailer-help-actions">
              {onSkip ? <Button type="button" variant="secondary" onClick={onSkip}
                data-testid={provider + '-mobile-skip'}>Winkel overslaan</Button> : null}
              <Button type="button" variant="secondary" onClick={onClose}
                data-testid={provider + '-help-ok'}>Terug naar Inhuis</Button>
            </div>
          </section>
        ) : (
          <>
            <p style={{ margin: 0 }}>Sleep de knop hieronder naar de favorietenbalk van je browser.
              Heb je al een oude {retailer}-favoriet? Vervang die eerst.</p>
            <a href={valid ? bookmarklet : undefined} data-testid={linkTestId}
              draggable={valid} aria-disabled={!valid} className="rz-retailer-desktop-bookmarklet"
              onClick={event => event.preventDefault()}>{retailer}-bonnen ophalen</a>
            <p style={{ margin: 0 }}>Klik op <strong>OK</strong> nadat je de favoriet hebt opgeslagen.
              {instructions}</p>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button type="button" onClick={onClose} data-testid={provider + '-help-ok'}>OK</Button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  )
}
