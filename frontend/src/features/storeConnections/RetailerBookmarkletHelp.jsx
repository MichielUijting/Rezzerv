import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import Button from '../../ui/Button'
import { detectMobileRetailerEnvironment } from './retailerMobileEnvironment.js'
import { copyRetailerBookmarklet, hasMobileBookmarkletSetup, rememberMobileBookmarkletSetup } from './universalRetailerBookmarklet.js'

/**
 * Does not silently install scripts, read retailer cookies or treat navigation
 * as a connection. The explicit retailer-side bookmarklet still performs the
 * actual import; server acknowledgements remain the only success proof.
 */
export default function RetailerBookmarkletHelp({
  provider, retailer, open, onClose, bookmarklet, valid = true,
  instructions, onOpenStore, onSkip, universalBookmarklet, setupKeys, preparedCopy, browserUrl,
  onboardingMode = false,
}) {
  const dialogRef = useRef(null)
  const manualRef = useRef(null)
  const [copyState, setCopyState] = useState('idle')
  const [manualCopy, setManualCopy] = useState(false)
  const [reuse, setReuse] = useState(false)
  const copySequence = useRef(0)
  const mobileBookmarklet = universalBookmarklet || bookmarklet
  const setupKey = universalBookmarklet ? setupKeys?.[provider] : null
  const environment = detectMobileRetailerEnvironment()
  const mobile = environment.device !== 'desktop'
  const supported = !mobile || environment.browser === 'safari' || environment.browser === 'chrome'
  const standalone = mobile && (window.matchMedia?.('(display-mode: standalone)')?.matches || navigator.standalone === true)

  useEffect(() => {
    if (!open) return undefined
    const previousFocus = document.activeElement
    const dialog = dialogRef.current
    if (mobile) {
      dialog?.focus()
      if (dialog) dialog.scrollTop = 0
    } else {
      dialog?.querySelector('[data-testid="' + provider + '-help-ok"]')?.focus()
    }
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
    if (!open || !mobile) return undefined
    const previous = document.title
    document.title = universalBookmarklet ? 'Inhuis' : 'Inhuis ' + retailer + '-bonnen'
    return () => { document.title = previous }
  }, [open, mobile, retailer, universalBookmarklet])

  useEffect(() => {
    if (!open || !mobile) return undefined
    const sequence = ++copySequence.current
    const alreadyPrepared = hasMobileBookmarkletSetup(setupKey)
    setReuse(alreadyPrepared)
    setManualCopy(false)
    setCopyState('idle')
    if (!alreadyPrepared && preparedCopy?.value === mobileBookmarklet) {
      setCopyState('copying')
      preparedCopy.promise.then(ok => {
        if (sequence === copySequence.current) setCopyState(ok ? 'copied' : 'idle')
      })
    }
    return () => { ++copySequence.current }
  }, [open, mobile, setupKey, mobileBookmarklet, preparedCopy])

  async function copyScript() {
    if (!valid || !mobileBookmarklet) return
    const sequence = ++copySequence.current
    setCopyState('copying')
    const ok = await copyRetailerBookmarklet(mobileBookmarklet)
    if (sequence !== copySequence.current) return
    setCopyState(ok ? 'copied' : 'manual')
    setManualCopy(!ok)
    if (!ok) requestAnimationFrame(() => { manualRef.current?.focus(); manualRef.current?.select() })
  }

  function openStore() {
    if (!valid || !supported || standalone) return
    // The click indicates that the user has completed the shown bookmark setup.
    // The hint skips repeat instructions, never import/authentication checks.
    if (mobile && !reuse && universalBookmarklet) rememberMobileBookmarkletSetup(setupKeys)
    onOpenStore?.()
  }

  if (!open) return null
  const titleId = provider + '-bookmarklet-help-title'
  const linkTestId = provider === 'jumbo' ? 'jumbo-poc-bookmarklet' : 'lidl-web-bookmarklet'
  const savedName = universalBookmarklet ? 'Inhuis' : 'Inhuis ' + retailer + '-bonnen'
  const desktopBookmarklet = onboardingMode ? universalBookmarklet : bookmarklet
  return createPortal(
    <div data-testid={provider + '-bookmarklet-help'} className="rz-retailer-help-backdrop">
      <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId}
        data-testid={provider + '-bookmarklet-dialog'} className="rz-retailer-help-dialog">
        <h3 id={titleId} style={{ margin: 0 }}>
          {mobile ? 'Koppel ' + retailer : 'Eerste keer koppelen met ' + retailer + '?'}
        </h3>
        {mobile ? (
          <section className="rz-retailer-mobile-setup" data-testid={provider + '-mobile-setup'}
            data-device={environment.device} data-browser={environment.browser}>
            {standalone ? (
              <>
                <p>Open deze pagina in {environment.device === 'iphone' ? 'Safari' : 'Chrome'} om je bladwijzer te gebruiken.</p>
                {browserUrl ? <a href={browserUrl} target="_blank" rel="noopener noreferrer"
                  className="rz-button-primary" role="button">Open in {environment.device === 'iphone' ? 'Safari' : 'Chrome'}</a> : null}
              </>
            ) : !supported ? (
              <p role="alert" data-testid={provider + '-browser-warning'}>
                Open Inhuis in {environment.device === 'iphone' ? 'Safari' : 'Chrome'}.
              </p>
            ) : reuse ? (
              <div className="rz-retailer-mobile-step">
                <p>Log zo nodig in bij {retailer}. Kies daarna de bladwijzer <strong>{savedName}</strong>.</p>
                <Button type="button" disabled={!valid} onClick={openStore}
                  data-testid={provider + '-mobile-open-store'}>Open {retailer}</Button>
                <Button type="button" variant="secondary" onClick={() => { setReuse(false); setCopyState('idle') }}>
                  Bladwijzer opnieuw instellen
                </Button>
              </div>
            ) : copyState === 'copying' ? (
              <p role="status">Adres voorbereiden…</p>
            ) : copyState === 'idle' ? (
              <div className="rz-retailer-mobile-step">
                <p>Stel één keer je bladwijzer <strong>{savedName}</strong> in.</p>
                <Button type="button" disabled={!valid} onClick={copyScript}
                  data-testid={provider + '-mobile-copy'}>Kopieer adres</Button>
              </div>
            ) : (
              <div className="rz-retailer-mobile-step">
                {manualCopy ? <div data-testid={provider + '-manual-copy'}>
                  <p>Kopieer het geselecteerde adres.</p>
                  <textarea ref={manualRef} readOnly rows={2} value={mobileBookmarklet}
                    aria-label="Adres handmatig kopiëren" onFocus={event => event.currentTarget.select()} />
                </div> : <small role="status">Adres gekopieerd.</small>}
                <p>{environment.device === 'iphone'
                  ? 'Delen → Voeg bladwijzer toe → Bewaar.'
                  : 'Chrome: ⋮ → ☆. Bewaar deze pagina.'}</p>
                <p>{environment.device === 'iphone'
                  ? 'Bladwijzers → Wijzig → ' + savedName + ' → vervang het adres en bewaar.'
                  : 'Bewerk de bladwijzer ' + savedName + ' → plak het adres → opslaan.'}</p>
                <Button type="button" disabled={!valid} onClick={openStore}
                  data-testid={provider + '-mobile-open-store'}>Open {retailer}</Button>
                <small>Log zo nodig in en kies daar de bladwijzer {savedName}.</small>
              </div>
            )}
            <div className="rz-retailer-help-actions">
              {onSkip ? <Button type="button" variant="secondary" onClick={onSkip}
                data-testid={provider + '-mobile-skip'}>Winkel overslaan</Button> : null}
              <Button type="button" variant="secondary" onClick={onClose}
                data-testid={provider + '-help-ok'}>Terug naar Inhuis</Button>
            </div>
          </section>
        ) : (
          <>
            <p style={{ margin: 0 }}>{onboardingMode
              ? 'Sleep Inhuis één keer naar je favorietenbalk. Dezelfde bladwijzer werkt voor Jumbo én Lidl, ook bij volgende imports.'
              : 'Sleep de knop hieronder naar de favorietenbalk van je browser. Heb je al een oude favoriet? Vervang die eerst.'}</p>
            <a href={valid ? desktopBookmarklet : undefined} data-testid={linkTestId}
              draggable={valid} aria-disabled={!valid} className="rz-retailer-desktop-bookmarklet"
              onClick={event => event.preventDefault()}>{onboardingMode ? 'Inhuis' : retailer + '-bonnen ophalen'}</a>
            <p style={{ margin: 0 }}>{onboardingMode
              ? <>Klik op <strong>Open {retailer}</strong>, meld je eventueel aan bij de winkel en kies daar de bladwijzer <strong>Inhuis</strong>.</>
              : <>Klik op <strong>OK</strong> nadat je de favoriet hebt opgeslagen. {instructions}</>}</p>
            <div className="rz-retailer-help-actions">
              {onboardingMode ? <Button type="button" onClick={openStore}
                data-testid={provider + '-desktop-open-store'}>Open {retailer}</Button> : null}
              {onSkip ? <Button type="button" variant="secondary" onClick={onSkip}>Winkel overslaan</Button> : null}
              <Button type="button" variant="secondary" onClick={onClose}
                data-testid={provider + '-help-ok'}>{onboardingMode ? 'Terug naar Inhuis' : 'OK'}</Button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  )
}
