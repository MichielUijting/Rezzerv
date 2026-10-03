import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMobileAppViewport } from '../../app/mobileViewport.js'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { canCurrentUserPerform, fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'
import CatalogCameraModal from './CatalogCameraModal'
import CatalogGpcFrame from './CatalogGpcFrame'
import CatalogProductImage from './CatalogProductImage'
import { captureCatalogImageFromVideo, compressCatalogImage } from './catalogImageCompression'
import './catalog.css'
import './mobileCatalog.css'

function text(value, fallback = '-') {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function sourceLabel(value) {
  const normalized = String(value ?? '').trim().toLowerCase()
  const labels = {
    receipt_user_confirmed: 'Door gebruiker bevestigd',
    receipt: 'Kassabon',
    user: 'Gebruiker',
    manual: 'Handmatig',
    catalog_gtin: 'Bestaande Catalogus-GTIN',
    openfoodfacts: 'Open Food Facts',
    open_food_facts: 'Open Food Facts',
    public_reference: 'Openbare referentie',
    gs1: 'GS1',
    ai: 'AI',
  }
  return labels[normalized] || text(value)
}

function identityTypeLabel(value) {
  const normalized = String(value ?? '').trim().toLowerCase()
  const labels = {
    gtin: 'GTIN',
    ean: 'EAN',
    upc: 'UPC',
    retailer_article_number: 'Winkelartikelnummer',
    external_article_number: 'Extern artikelnummer',
    store_sku: 'Winkelcode',
    text_match: 'Tekstherkenning',
  }
  return labels[normalized] || text(value)
}

export default function CatalogDetailPageV2() {
  const { globalProductId = '' } = useParams()
  const navigate = useNavigate()
  const isMobileViewport = useMobileAppViewport()
  const { showFeedback } = useAppFeedback()
  const authContext = readStoredAuthContext()
  const canUpdateCatalogImage = canCurrentUserPerform('platform.catalog.update', authContext)
  const uploadInputRef = useRef(null)
  const cameraVideoRef = useRef(null)
  const cameraStreamRef = useRef(null)
  const [detail, setDetail] = useState(null)
  const [confirmedProductType, setConfirmedProductType] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isImageSaving, setIsImageSaving] = useState(false)
  const [isCameraOpen, setIsCameraOpen] = useState(false)
  const [cameraState, setCameraState] = useState({ status: 'idle', message: '' })
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function loadDetail() {
      setIsLoading(true)
      setError('')
      try {
        const response = await fetchJsonWithAuth(
          `/api/catalog/${encodeURIComponent(globalProductId)}`,
          { method: 'GET' },
        )
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(data?.detail || 'Catalogusartikel kon niet worden geladen')
        }
        if (!cancelled) setDetail(data)
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError?.message || 'Catalogusartikel kon niet worden geladen')
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    loadDetail()
    return () => { cancelled = true }
  }, [globalProductId])

  useEffect(() => {
    if (!isCameraOpen) return
    const video = cameraVideoRef.current
    const stream = cameraStreamRef.current
    if (!video || !stream) return

    video.srcObject = stream
    video.play().catch(() => {
      setCameraState({
        status: 'error',
        message: 'Het live camerabeeld kon niet worden gestart.',
      })
    })
  }, [isCameraOpen, cameraState.status])

  useEffect(() => () => {
    cameraStreamRef.current?.getTracks?.().forEach((track) => track.stop())
    cameraStreamRef.current = null
  }, [])

  const product = detail?.product || {}
  const identities = Array.isArray(detail?.identities) ? detail.identities : []
  const householdArticles = Array.isArray(detail?.household_articles) ? detail.household_articles : []
  const receiptLines = Array.isArray(detail?.receipt_lines) ? detail.receipt_lines : []
  const productType = confirmedProductType || product.product_type

  function handleGpcAssignmentChange(assignment) {
    const description = String(assignment?.brick_description || assignment?.brick_description_en || '').trim()
    setConfirmedProductType(description)
    setDetail((current) => current
      ? {
          ...current,
          product: {
            ...(current.product || {}),
            product_type: description,
            gpc_brick_code: assignment?.brick_code || null,
            gpc_class_code: assignment?.class_code || null,
            gpc_class_name: assignment?.class_description || '',
            gpc_family_code: assignment?.family_code || null,
            gpc_family_name: assignment?.family_description || '',
          },
        }
      : current)
  }

  function openImageChoice() {
    if (!canUpdateCatalogImage || isImageSaving) return
    showFeedback({
      variant: 'info',
      title: product.image_url ? 'Productfoto wijzigen' : 'Productfoto toevoegen',
      message: 'Hoe wil je de foto toevoegen?',
      detail: 'De foto wordt automatisch verkleind en gecomprimeerd voordat hij wordt opgeslagen.',
      testId: 'catalog-image-source-choice',
      primaryActionLabel: 'Foto uploaden',
      secondaryActionLabel: 'Foto maken',
      onPrimaryAction: () => uploadInputRef.current?.click(),
      onSecondaryAction: startCamera,
    })
  }

  function cameraErrorMessage(cameraError) {
    const name = String(cameraError?.name || '')
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      return 'Cameratoegang is geweigerd. Sta cameragebruik toe in de browser en probeer opnieuw.'
    }
    if (name === 'NotFoundError' || name === 'OverconstrainedError') {
      return 'Er is geen bruikbare camera op dit toestel gevonden.'
    }
    if (name === 'NotReadableError' || name === 'AbortError') {
      return 'De camera kan niet worden geopend. Mogelijk wordt deze al door een andere app gebruikt.'
    }
    return cameraError?.message || 'De camera kon niet worden geopend.'
  }

  async function startCamera() {
    setIsCameraOpen(true)
    setCameraState({ status: 'starting', message: 'Camera wordt gestart…' })

    const getUserMedia = navigator.mediaDevices?.getUserMedia
    if (typeof getUserMedia !== 'function') {
      setCameraState({
        status: 'error',
        message: 'Deze browser ondersteunt geen live cameratoegang.',
      })
      return
    }

    try {
      cameraStreamRef.current?.getTracks?.().forEach((track) => track.stop())
      const stream = await getUserMedia.call(navigator.mediaDevices, {
        audio: false,
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 1280 },
        },
      })
      cameraStreamRef.current = stream
      setCameraState({ status: 'connected', message: 'Camera wordt voorbereid…' })
    } catch (cameraError) {
      setCameraState({ status: 'error', message: cameraErrorMessage(cameraError) })
    }
  }

  function handleCameraReady() {
    setCameraState({ status: 'ready', message: 'Camera gereed.' })
  }

  function closeCamera() {
    cameraStreamRef.current?.getTracks?.().forEach((track) => track.stop())
    cameraStreamRef.current = null
    if (cameraVideoRef.current) cameraVideoRef.current.srcObject = null
    setIsCameraOpen(false)
    setCameraState({ status: 'idle', message: '' })
  }

  async function persistCatalogImage(file) {
    setIsImageSaving(true)
    try {
      const imageDataUrl = await compressCatalogImage(file)
      const response = await fetchJsonWithAuth(
        `/api/catalog/${encodeURIComponent(globalProductId)}/image`,
        {
          method: 'PUT',
          body: JSON.stringify({ image_data_url: imageDataUrl }),
        },
      )
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'Productfoto kon niet worden opgeslagen')
      }

      setDetail((current) => current
        ? {
            ...current,
            product: {
              ...(current.product || {}),
              image_url: data.image_url || imageDataUrl,
            },
          }
        : current)
      showFeedback({
        variant: 'success',
        title: 'Productfoto opgeslagen',
        message: 'De foto is toegevoegd aan het catalogusartikel.',
      })
    } catch (imageError) {
      showFeedback({
        variant: 'error',
        title: 'Productfoto niet opgeslagen',
        message: imageError?.message || 'De productfoto kon niet worden opgeslagen.',
      })
    } finally {
      setIsImageSaving(false)
    }
  }

  async function handleImageFile(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    await persistCatalogImage(file)
  }

  async function handleCameraCapture() {
    if (cameraState.status !== 'ready') return
    setCameraState({ status: 'capturing', message: 'Foto wordt gemaakt…' })
    try {
      const photo = await captureCatalogImageFromVideo(cameraVideoRef.current)
      closeCamera()
      await persistCatalogImage(photo)
    } catch (captureError) {
      setCameraState({
        status: 'error',
        message: captureError?.message || 'De foto kon niet worden gemaakt.',
      })
    }
  }

  if (isMobileViewport) {
    return (
      <div className="rz-screen rz-mobile-catalog-detail-screen" data-testid="mobile-catalog-detail-page">
        <MobileModuleHeader
          title="Catalogusdetail"
          testId="mobile-catalog-detail-header"
          showBack
          onBack={() => navigate('/catalogus')}
        />
        <main className="rz-mobile-catalog-detail-content">
          {isLoading ? <section className="rz-mobile-catalog-state">Catalogusartikel laden…</section> : null}
          {error ? <section className="rz-mobile-catalog-state" role="alert">{error}</section> : null}

          {!isLoading && !error ? (
            <>
              <section className="rz-mobile-catalog-detail-card rz-mobile-catalog-detail-summary">
                <div className="rz-catalog-product-image-editor">
                  {canUpdateCatalogImage ? (
                    <>
                      <button
                        type="button"
                        className="rz-catalog-product-image-action"
                        onClick={openImageChoice}
                        disabled={isImageSaving}
                        aria-label={product.image_url ? 'Productfoto wijzigen' : 'Productfoto toevoegen'}
                        aria-busy={isImageSaving ? 'true' : undefined}
                        data-testid="mobile-catalog-product-image-action"
                      >
                        <CatalogProductImage imageUrl={product.image_url} productName={product.name} />
                        <span className="rz-catalog-product-image-action-label">
                          {isImageSaving ? 'Foto verwerken…' : product.image_url ? 'Foto wijzigen' : 'Foto toevoegen'}
                        </span>
                      </button>
                      <input
                        ref={uploadInputRef}
                        className="rz-catalog-product-image-input"
                        type="file"
                        accept="image/*"
                        onChange={handleImageFile}
                        aria-label="Productfoto uploaden"
                      />
                    </>
                  ) : <CatalogProductImage imageUrl={product.image_url} productName={product.name} />}
                </div>
                <div className="rz-mobile-catalog-detail-summary-copy">
                  <h2>{text(product.name, 'Universeel artikel')}</h2>
                  <dl>
                    <div><dt>Merk</dt><dd>{text(product.brand)}</dd></div>
                    <div><dt>Primaire GTIN</dt><dd>{text(product.primary_gtin)}</dd></div>
                    <div><dt>Producttype</dt><dd>{text(productType, 'Nog niet geclassificeerd')}</dd></div>
                    <div><dt>GPC-familie</dt><dd>{text(product.gpc_family_name, 'Niet geclassificeerd')}</dd></div>
                    <div><dt>Bron</dt><dd>{sourceLabel(product.source)}</dd></div>
                  </dl>
                </div>
              </section>

              <section className="rz-mobile-catalog-detail-card rz-mobile-catalog-gpc">
                <CatalogGpcFrame globalProductId={globalProductId} onAssignmentChange={handleGpcAssignmentChange} />
              </section>

              <section className="rz-mobile-catalog-detail-card">
                <h3>Identiteiten</h3>
                <div className="rz-mobile-catalog-detail-list">
                  {identities.length ? identities.map((identity, index) => (
                    <div className="rz-mobile-catalog-detail-item" key={identity.id || `${identity.identity_type}-${identity.identity_value}-${index}`}>
                      <strong>{identityTypeLabel(identity.identity_type)} · {text(identity.identity_value)}</strong>
                      <span>{identity.is_primary ? 'Primair' : 'Niet primair'} · {sourceLabel(identity.source)}</span>
                    </div>
                  )) : <span>Geen aanvullende identiteiten gevonden.</span>}
                </div>
              </section>

              <section className="rz-mobile-catalog-detail-card">
                <h3>Gekoppelde huishoudartikelen</h3>
                <div className="rz-mobile-catalog-detail-list">
                  {householdArticles.length ? householdArticles.map((article, index) => (
                    <div className="rz-mobile-catalog-detail-item" key={article.id || index}>
                      <strong>{text(article.name || article.article_name)}</strong>
                      <span>Minimum {text(article.minimum_stock)} · Ideaal {text(article.ideal_stock)}</span>
                    </div>
                  )) : <span>Geen gekoppelde huishoudartikelen gevonden.</span>}
                </div>
              </section>

              <section className="rz-mobile-catalog-detail-card">
                <h3>Gekoppelde kassabonregels</h3>
                <div className="rz-mobile-catalog-detail-list">
                  {receiptLines.length ? receiptLines.map((line, index) => (
                    <div className="rz-mobile-catalog-detail-item" key={line.id || index}>
                      <strong>{text(line.article_name_raw)}</strong>
                      <span>{text(line.household_article_name)} · GTIN {text(line.gtin)}</span>
                    </div>
                  )) : <span>Geen gekoppelde kassabonregels gevonden.</span>}
                </div>
              </section>
            </>
          ) : null}
        </main>
        <CatalogCameraModal
          open={isCameraOpen}
          videoRef={cameraVideoRef}
          cameraState={cameraState}
          onVideoReady={handleCameraReady}
          onCapture={handleCameraCapture}
          onClose={closeCamera}
        />
      </div>
    )
  }

  return (
    <AppShell title="Catalogusdetail" showExit={false}>
      <div className="rz-catalog-page" data-testid="catalog-detail-page">
        <ScreenCard fullWidth>
          {isLoading ? <div>Catalogusartikel laden…</div> : null}
          {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}

          {!isLoading && !error ? (
            <div className="rz-catalog-detail-grid">
              <section className="rz-catalog-detail-section">
                <div className="rz-catalog-product-summary">
                  <div className="rz-catalog-product-image-editor">
                    {canUpdateCatalogImage ? (
                      <>
                        <button
                          type="button"
                          className="rz-catalog-product-image-action"
                          onClick={openImageChoice}
                          disabled={isImageSaving}
                          aria-label={product.image_url ? 'Productfoto wijzigen' : 'Productfoto toevoegen'}
                          aria-busy={isImageSaving ? 'true' : undefined}
                          data-testid="catalog-product-image-action"
                        >
                          <CatalogProductImage imageUrl={product.image_url} productName={product.name} />
                          <span className="rz-catalog-product-image-action-label">
                            {isImageSaving
                              ? 'Foto verwerken…'
                              : product.image_url
                                ? 'Foto wijzigen'
                                : 'Foto toevoegen'}
                          </span>
                        </button>
                        <input
                          ref={uploadInputRef}
                          className="rz-catalog-product-image-input"
                          type="file"
                          accept="image/*"
                          onChange={handleImageFile}
                          data-testid="catalog-image-upload-input"
                          aria-label="Productfoto uploaden"
                        />
                      </>
                    ) : (
                      <CatalogProductImage imageUrl={product.image_url} productName={product.name} />
                    )}
                  </div>
                  <div className="rz-catalog-product-summary-content">
                    <h2>{text(product.name, 'Universeel artikel')}</h2>
                    <dl className="rz-catalog-definition-list">
                      <div><dt>Merk</dt><dd>{text(product.brand)}</dd></div>
                      <div><dt>Primaire GTIN</dt><dd>{text(product.primary_gtin)}</dd></div>
                      <div><dt>Producttype</dt><dd>{text(productType, 'Nog niet geclassificeerd')}</dd></div>
                      <div><dt>GPC-familie</dt><dd>{text(product.gpc_family_name, 'Niet geclassificeerd')}</dd></div>
                      <div><dt>Bron</dt><dd>{sourceLabel(product.source)}</dd></div>
                    </dl>
                  </div>
                </div>
              </section>

              <CatalogGpcFrame globalProductId={globalProductId} onAssignmentChange={handleGpcAssignmentChange} />

              <section className="rz-catalog-detail-section">
                <h3>Identiteiten</h3>
                <Table dataTestId="catalog-identities-table" tableClassName="rz-catalog-detail-table" tableStyle={{ tableLayout: 'fixed', width: '100%' }}>
                  <colgroup><col style={{ width: '25%' }} /><col style={{ width: '25%' }} /><col style={{ width: '25%' }} /><col style={{ width: '25%' }} /></colgroup>
                  <thead>
                    <tr className="rz-table-header">
                      <th>Type</th><th>Waarde</th><th>Primair</th><th>Bron</th>
                    </tr>
                  </thead>
                  <tbody>
                    {identities.length ? identities.map((identity, index) => (
                      <tr key={identity.id || `${identity.identity_type}-${identity.identity_value}-${index}`}>
                        <td>{identityTypeLabel(identity.identity_type)}</td>
                        <td>{text(identity.identity_value)}</td>
                        <td>{identity.is_primary ? 'Ja' : 'Nee'}</td>
                        <td>{sourceLabel(identity.source)}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan="4">Geen aanvullende identiteiten gevonden.</td></tr>
                    )}
                  </tbody>
                </Table>
              </section>

              <section className="rz-catalog-detail-section">
                <h3>Gekoppelde huishoudartikelen</h3>
                <Table dataTestId="catalog-household-articles-table" tableClassName="rz-catalog-detail-table" tableStyle={{ tableLayout: 'fixed', width: '100%' }}>
                  <colgroup><col style={{ width: '25%' }} /><col style={{ width: '25%' }} /><col style={{ width: '25%' }} /><col style={{ width: '25%' }} /></colgroup>
                  <thead>
                    <tr className="rz-table-header">
                      <th>Huishouden</th><th>Huishoudartikel</th><th>Minimum</th><th>Ideaal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {householdArticles.length ? householdArticles.map((article, index) => (
                      <tr key={article.id || index}>
                        <td>{text(article.household_id)}</td>
                        <td>{text(article.name || article.article_name)}</td>
                        <td>{text(article.minimum_stock)}</td>
                        <td>{text(article.ideal_stock)}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan="4">Geen gekoppelde huishoudartikelen gevonden.</td></tr>
                    )}
                  </tbody>
                </Table>
              </section>

              <section className="rz-catalog-detail-section">
                <h3>Gekoppelde kassabonregels</h3>
                <Table dataTestId="catalog-receipt-lines-table" tableClassName="rz-catalog-detail-table" tableStyle={{ tableLayout: 'fixed', width: '100%' }}>
                  <colgroup><col style={{ width: '33.333%' }} /><col style={{ width: '33.333%' }} /><col style={{ width: '33.334%' }} /></colgroup>
                  <thead>
                    <tr className="rz-table-header">
                      <th>Bonartikel</th><th>Huishoudartikel</th><th>GTIN</th>
                    </tr>
                  </thead>
                  <tbody>
                    {receiptLines.length ? receiptLines.map((line, index) => (
                      <tr key={line.id || index}>
                        <td>{text(line.article_name_raw)}</td>
                        <td>{text(line.household_article_name)}</td>
                        <td>{text(line.gtin)}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan="3">Geen gekoppelde kassabonregels gevonden.</td></tr>
                    )}
                  </tbody>
                </Table>
              </section>
            </div>
          ) : null}
        </ScreenCard>

        <CatalogCameraModal
          open={isCameraOpen}
          videoRef={cameraVideoRef}
          cameraState={cameraState}
          onVideoReady={handleCameraReady}
          onCapture={handleCameraCapture}
          onClose={closeCamera}
        />
      </div>
    </AppShell>
  )
}
