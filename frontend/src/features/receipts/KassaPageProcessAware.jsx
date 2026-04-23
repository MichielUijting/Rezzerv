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
.toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-bottom:16px; }
.label { font-size:14px; font-weight:700; color:#344054; }
.select { padding:8px 12px; border:1px solid #d0d5dd; border-radius:8px; background:#fff; font-size:14px; }
.meta { font-size:13px; color:#667085; }
.stage { background:#fff; border:1px solid #d0d5dd; border-radius:12px; padding:12px; }
.canvas-wrap { display:none; }
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
    <img id="visibleImage" src="${safeDataUrl}" alt="Kassabon" />
    <div class="canvas-wrap"><canvas id="grayCanvas"></canvas></div>
    <div class="canvas-wrap"><canvas id="thresholdCanvas"></canvas></div>
  </div>

  <img id="sourceImage" src="${safeDataUrl}" alt="Bron" style="display:none;" />

<script>
const select = document.getElementById('stepSelect')
const visibleImage = document.getElementById('visibleImage')
const sourceImage = document.getElementById('sourceImage')
const grayCanvas = document.getElementById('grayCanvas')
const thresholdCanvas = document.getElementById('thresholdCanvas')
let grayReady = false
let thresholdReady = false

function renderStage(stage) {
  if (stage === 'original') {
    visibleImage.style.display = 'block'
    visibleImage.src = sourceImage.src
    return
  }
  if (stage === 'gray' && grayReady) {
    visibleImage.style.display = 'block'
    visibleImage.src = grayCanvas.toDataURL('image/png')
    return
  }
  if (stage === 'threshold' && thresholdReady) {
    visibleImage.style.display = 'block'
    visibleImage.src = thresholdCanvas.toDataURL('image/png')
    return
  }
  visibleImage.style.display = 'block'
  visibleImage.src = sourceImage.src
}

sourceImage.onload = () => {
  const w = sourceImage.naturalWidth || sourceImage.width
  const h = sourceImage.naturalHeight || sourceImage.height
  if (!w || !h) {
    renderStage(select.value)
    return
  }

  grayCanvas.width = w
  grayCanvas.height = h
  thresholdCanvas.width = w
  thresholdCanvas.height = h

  const grayCtx = grayCanvas.getContext('2d')
  const thresholdCtx = thresholdCanvas.getContext('2d')
  grayCtx.drawImage(sourceImage, 0, 0, w, h)
  const grayData = grayCtx.getImageData(0, 0, w, h)
  for (let i = 0; i < grayData.data.length; i += 4) {
    const avg = (grayData.data[i] + grayData.data[i + 1] + grayData.data[i + 2]) / 3
    grayData.data[i] = avg
    grayData.data[i + 1] = avg
    grayData.data[i + 2] = avg
  }
  grayCtx.putImageData(grayData, 0, 0)
  grayReady = true

  const thresholdData = grayCtx.getImageData(0, 0, w, h)
  for (let i = 0; i < thresholdData.data.length; i += 4) {
    const value = thresholdData.data[i] > 150 ? 255 : 0
    thresholdData.data[i] = value
    thresholdData.data[i + 1] = value
    thresholdData.data[i + 2] = value
  }
  thresholdCtx.putImageData(thresholdData, 0, 0)
  thresholdReady = true
  renderStage(select.value)
}

select.addEventListener('change', (event) => renderStage(event.target.value))
renderStage('original')
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
.toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-bottom:16px; }
.label { font-size:14px; font-weight:700; color:#344054; }
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

function mountLocalPreview(file) {
  const cardRoot = document.querySelector('[data-testid="receipt-preview-card"] > div')
  if (!cardRoot || !file) return

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

  container.appendChild(helper)
  container.appendChild(frame)

  const anchor = cardRoot.firstElementChild?.nextElementSibling
  if (anchor) cardRoot.insertBefore(container, anchor)
  else cardRoot.appendChild(container)

  if (String(file.type || '').startsWith('image/')) {
    const reader = new FileReader()
    reader.onload = () => {
      frame.srcdoc = buildImageProcessHtml(String(reader.result || ''), file.name || 'Kassabon')
    }
    reader.readAsDataURL(file)
    return
  }

  if (String(file.type || '').includes('pdf') || String(file.name || '').toLowerCase().endsWith('.pdf')) {
    const blobUrl = URL.createObjectURL(file)
    frame.srcdoc = buildPdfProcessHtml(blobUrl, file.name || 'Kassabon')
  }
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

    const onFileInputChange = (event) => {
      const file = findSupportedReceiptFileFromEventTarget(event.target)
      if (file) mountLocalPreview(file)
    }

    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input?.url || ''
      const response = await originalFetch(input, init)

      try {
        if (response.ok && url.includes('/api/receipts/') && url.endsWith('/preview')) {
          removeLocalPreview()
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
      removeLocalPreview()
    }
  }, [])

  return <KassaPage />
}
