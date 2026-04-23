import { useEffect } from 'react'
import KassaPage from './KassaPage.jsx'

// Intercepts preview image and replaces it with HTML that visualizes processing steps
export default function KassaPageProcessAware() {
  useEffect(() => {
    const originalFetch = window.fetch

    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input?.url || ''
      const response = await originalFetch(input, init)

      try {
        if (response.ok && url.includes('/api/receipts/') && url.endsWith('/preview')) {
          const contentType = response.headers.get('content-type') || ''
          if (contentType.startsWith('image/')) {
            const blob = await response.blob()
            const reader = new FileReader()

            const dataUrl = await new Promise((resolve, reject) => {
              reader.onload = () => resolve(reader.result)
              reader.onerror = reject
              reader.readAsDataURL(blob)
            })

            const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
body { font-family: sans-serif; background:#f8fafc; margin:0; padding:16px; }
.section { margin-bottom:24px; }
.title { font-weight:700; margin-bottom:8px; }
canvas, img { max-width:100%; border-radius:4px; background:#fff; }
</style>
</head>
<body>
<div class="section">
<div class="title">Stap 1: Origineel</div>
<img id="orig" src="${dataUrl}" />
</div>
<div class="section">
<div class="title">Stap 2: Grayscale (OCR voorbereiding)</div>
<canvas id="gray"></canvas>
</div>
<div class="section">
<div class="title">Stap 3: Threshold (OCR-ready)</div>
<canvas id="th"></canvas>
</div>
<script>
const img = document.getElementById('orig')
const gray = document.getElementById('gray')
const th = document.getElementById('th')

img.onload = () => {
  const w = img.naturalWidth
  const h = img.naturalHeight

  gray.width = w; gray.height = h
  th.width = w; th.height = h

  const gctx = gray.getContext('2d')
  const tctx = th.getContext('2d')

  gctx.drawImage(img,0,0)
  const imgData = gctx.getImageData(0,0,w,h)

  for(let i=0;i<imgData.data.length;i+=4){
    const avg = (imgData.data[i]+imgData.data[i+1]+imgData.data[i+2])/3
    imgData.data[i]=imgData.data[i+1]=imgData.data[i+2]=avg
  }
  gctx.putImageData(imgData,0,0)

  const thData = gctx.getImageData(0,0,w,h)
  for(let i=0;i<thData.data.length;i+=4){
    const val = thData.data[i] > 150 ? 255 : 0
    thData.data[i]=thData.data[i+1]=thData.data[i+2]=val
  }
  tctx.putImageData(thData,0,0)
}
</script>
</body>
</html>`

            return new Response(html, {
              status: 200,
              headers: { 'Content-Type': 'text/html' }
            })
          }
        }
      } catch (e) {
        // fallback silently
      }

      return response
    }

    return () => {
      window.fetch = originalFetch
    }
  }, [])

  return <KassaPage />
}
