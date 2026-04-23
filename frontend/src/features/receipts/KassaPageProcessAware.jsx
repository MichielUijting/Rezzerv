import { useEffect } from 'react'
import KassaPage from './KassaPage.jsx'

const LOCAL_PREVIEW_CONTAINER_ID = 'rezzerv-local-receipt-preview'

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function buildImageProcessHtml(dataUrl, fileName = 'Kassabon') {
  const safeFileName = escapeHtml(fileName)
  const safeDataUrl = escapeHtml(dataUrl)
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body { font-family: sans-serif; background:#f8fafc; margin:0; padding:16px; color:#101828; }
.toolbar { display:flex; flex-wrap:wrap; align-items:end; gap:12px; margin-bottom:16px; }
.label { font-size:14px; font-weight:700; color:#344054; margin-bottom:6px; }
.select { padding:8px 12px; border:1px solid #d0d5dd; border-radius:8px; background:#fff; font-size:14px; }
.meta { font-size:13px; color:#667085; }
.stage { background:#fff; border:1px solid #d0d5dd; border-radius:12px; padding:12px; }
.stage-panel { display:none; }
.stage-panel.active { display:block; }
img, canvas { display:block; width:100%; height:auto; border-radius:8px; background:#fff; }
</style>
</head>
<body>
  <div class="toolbar">
    <div>
      <div class="label">Weergave</div>
      <select id="stepSelect" class="select" aria-label="Kies kassabonstap">
        <option value="original">Origineel</option>
        <option value="gray">Genormaliseerd</option>
        <option value="threshold">OCR-ready</option>
      </select>
    </div>
    <div class="meta">${safeFileName}</div>
  </div>

  <div class="stage">
    <div id="panel-original" class="stage-panel active">
      <img id="originalImage" src="${safeDataUrl}" alt="Originele kassabon" />
    </div>
    <div id="panel-gray" class="stage-panel">
      <canvas id="grayCanvas"></canvas>
    </div>
    <div id="panel-threshold" class="stage-panel">
      <canvas id="thresholdCanvas"></canvas>
    </div>
  </div>

<script>
const select = document.getElementById('stepSelect')
const originalImage = document.getElementById('originalImage')
const grayCanvas = document.getElementById('grayCanvas')
const thresholdCanvas = document.getElementById('thresholdCanvas')
const panels = {
  original: document.getElementById('panel-original'),
  gray: document.getElementById('panel-gray'),
  threshold: document.getElementById('panel-threshold'),
}

function showStage(stage) {
  Object.entries(panels).forEach(([key, panel]) => {
    if (!panel) return
    panel.className = key === stage ? 'stage-panel active' : 'stage-panel'
  })
}

function renderDerivedStages() {
  const width = originalImage.naturalWidth || originalImage.width
  const height = originalImage.naturalHeight || originalImage.height
  if (!width || !height) return

  grayCanvas.width = width
  grayCanvas.height = height
  thresholdCanvas.width = width
  thresholdCanvas.height = height

  const grayCtx = grayCanvas.getContext('2d')
  const thresholdCtx = thresholdCanvas.getContext('2d')
  grayCtx.drawImage(originalImage, 0, 0, width, height)
  const grayData = grayCtx.getImageData(0, 0, width, height)
  for (let index = 0; index < grayData.data.length; index += 4) {
    const avg = (grayData.data[index] + grayData.data[index + 1] + grayData.data[index + 2]) / 3
    grayData.data[index] = avg
    grayData.data[index + 1] = avg
    grayData.data[index + 2] = avg
  }
  grayCtx.putImageData(grayData, 0, 0)

  const thresholdData = grayCtx.getImageData(0, 0, width, height)
  for (let index = 0; index < thresholdData.data.length; index += 4) {
    const value = thresholdData.data[index] > 150 ? 255 : 0
    thresholdData.data[index] = value
    thresholdData.data[index + 1] = value
    thresholdData.data[index + 2] = value
  }
  thresholdCtx.putImageData(thresholdData, 0, 0)
}

originalImage.addEventListener('load', () => {
  renderDerivedStages()
  showStage(select.value || 'original')
})

select.addEventListener('change', (event) => {
  showStage(event.target.value || 'original')
})

showStage('original')
if (originalImage.complete) {
  renderDerivedStages()
}
</script>
</body>
</html>`
}

function buildPdfProcessHtml(blobUrl, fileName = 'Kassabon') {
  const safeFileName = escapeHtml(fileName)
  const safeBlobUrl = escapeHtml(blobUrl)
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body { font-family: sans-serif; background:#f8fafc; margin:0; padding:16px; color:#101828; }
.toolbar { display:flex; flex-wrap:wrap; align-items:end; gap:12px; margin-bottom:16px; }
.label { font-size:14px; font-weight:700; color:#344054; margin-bottom:6px; }
.select { padding:8px 12px; border:1px solid #d0d5dd; border-radius:8px; background:#fff; font-size:14px; }
.meta { font-size:13px; color:#667085; }
.stage { background:#fff; border:1px solid #d0d5dd; border-radius:12px; overflow:hidden; }
iframe { display:block; width:100%; height:75vh; min-height:720px; border:0; background:#fff; }
</style>
</head>
<body>
  <div class="toolbar">
    <div>
      <div class="label">Weergave</div>
      <select class="select" aria-label="Kies kassabonstap" disabled>
        <option>Origineel</option>
      </select>
    </div>
    <div class="meta">${safeFileName}</div>
  </div>
  <div class="stage">
    <iframe src="${safeBlobUrl}#toolbar=1&navpanes=0&scrollbar=1&zoom=page-width" title="PDF kassabon"></iframe>
  </div>
</body>
</html>`
}

function removeLocalPreview() {
  const existing = document.getElementById(LOCAL_PREVIEW_CONTAINER_ID)
  if (existing) existing.remove()
}

function getPreviewCardRoot() {
  return document.querySelector('[data-testid="receipt-preview-card"] > div')
}

function insertPreviewIntoCard(srcdoc) {
  const cardRoot = getPreviewCardRoot()
  if (!cardRoot) return false

  removeLocalPreview()

  const container = document.createElement('div')
  container.id = LOCAL_PREVIEW_CONTAINER_ID
  container.style.display = 'grid'
  container.style.gap = '12px'
  container.style.marginBottom = '12px'

  const helper = document.createElement('div')
  helper.style.fontSize = '13px'
  helper.style.color = '#667085'
  helper.style.fontWeight = '600'
  helper.textContent = 'Lokale preview bij start van het inlezen. Na upload neemt de verwerkte preview hieronder het over.'

  const frame = document.createElement('iframe')
  frame.title = 'Lokale kassabonpreview'
  frame.style.display = 'block'
  frame.style.width = '100%'
  frame.style.height = '42vh'
  frame.style.minHeight = '420px'
  frame.style.border = '1px solid #d0d5dd'
  frame.style.borderRadius = '12px'
  frame.style.background = '#fff'
  frame.srcdoc = srcdoc

  container.appendChild(helper)
  container.appendChild(frame)

  const anchor = cardRoot.firstElementChild?.nextElementSibling
  if (anchor) cardRoot.insertBefore(container, anchor)
  else cardRoot.appendChild(container)
  return true
}

function buildPreviewSrcdocFromFile(file) {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error('Geen bestand beschikbaar voor preview.'))
      return
    }
    const fileType = String(file.type || '').toLowerCase()
    const fileName = String(file.name || 'Kassabon')
    if (fileType.startsWith('image/')) {
      const reader = new FileReader()
      reader.onload = () => resolve(buildImageProcessHtml(String(reader.result || ''), fileName))
      reader.onerror = () => reject(new Error('Lokale afbeelding kon niet worden gelezen.'))
      reader.readAsDataURL(file)
      return
    }
    if (fileType.includes('pdf') || fileName.toLowerCase().endsWith('.pdf')) {
      const blobUrl = URL.createObjectURL(file)
      resolve(buildPdfProcessHtml(blobUrl, fileName))
      return
    }
    reject(new Error('Bestandstype wordt niet ondersteund voor lokale preview.'))
  })
}

function findSupportedReceiptFileFromEventTarget(target) {
  const files = Array.from(target?.files || [])
  return files.find((file) => {
    const type = String(file?.type || '').toLowerCase()
    const name = String(file?.name || '').toLowerCase()
    return type.startsWith('image/') || type.includes('pdf') || name.endsWith('.pdf')
  }) || null
}

export default function KassaPageProcessAware() {
  useEffect(() => {
    const originalFetch = window.fetch
    let pendingPreviewSrcdoc = ''

    const tryMountPendingPreview = () => {
      if (!pendingPreviewSrcdoc) return
      const mounted = insertPreviewIntoCard(pendingPreviewSrcdoc)
      if (mounted) pendingPreviewSrcdoc = ''
    }

    const mutationObserver = new MutationObserver(() => {
      tryMountPendingPreview()
    })
    mutationObserver.observe(document.body, { childList: true, subtree: true })

    const onFileInputChange = async (event) => {
      const file = findSupportedReceiptFileFromEventTarget(event.target)
      if (!file) return
      try {
        pendingPreviewSrcdoc = await buildPreviewSrcdocFromFile(file)
        tryMountPendingPreview()
      } catch {
        pendingPreviewSrcdoc = ''
      }
    }

    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input?.url || ''
      const response = await originalFetch(input, init)

      try {
        if (response.ok && url.includes('/api/receipts/') && url.endsWith('/preview')) {
          removeLocalPreview()
          pendingPreviewSrcdoc = ''
          const contentType = response.headers.get('content-type') || ''
          if (contentType.startsWith('image/')) {
            const blob = await response.blob()
            const reader = new FileReader()
            const dataUrl = await new Promise((resolve, reject) => {
              reader.onload = () => resolve(reader.result)
              reader.onerror = reject
              reader.readAsDataURL(blob)
            })
            return new Response(buildImageProcessHtml(String(dataUrl || ''), 'Kassabon'), {
              status: 200,
              headers: { 'Content-Type': 'text/html' },
            })
          }
          if (contentType.includes('pdf')) {
            const blob = await response.blob()
            const blobUrl = URL.createObjectURL(blob)
            return new Response(buildPdfProcessHtml(blobUrl, 'Kassabon'), {
              status: 200,
              headers: { 'Content-Type': 'text/html' },
            })
          }
        }
      } catch {
        // fallback silently
      }

      return response
    }

    document.addEventListener('change', onFileInputChange, true)

    return () => {
      window.fetch = originalFetch
      document.removeEventListener('change', onFileInputChange, true)
      mutationObserver.disconnect()
      pendingPreviewSrcdoc = ''
      removeLocalPreview()
    }
  }, [])

  return <KassaPage />
}
