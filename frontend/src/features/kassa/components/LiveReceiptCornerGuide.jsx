import { useEffect, useRef } from 'react'

function drawGuide(canvas, video, result, fit) {
  const rect = video.getBoundingClientRect()
  const width = Math.max(1, Math.round(rect.width))
  const height = Math.max(1, Math.round(rect.height))
  if (canvas.width !== width) canvas.width = width
  if (canvas.height !== height) canvas.height = height

  const context = canvas.getContext('2d')
  if (!context) return
  context.clearRect(0, 0, width, height)

  const corners = Array.isArray(result?.corners) ? result.corners : null
  const sourceWidth = Number(result?.image_width || 0)
  const sourceHeight = Number(result?.image_height || 0)
  if (!corners || corners.length !== 4 || !sourceWidth || !sourceHeight) return

  const scale = fit === 'contain'
    ? Math.min(width / sourceWidth, height / sourceHeight)
    : Math.max(width / sourceWidth, height / sourceHeight)
  const drawnWidth = sourceWidth * scale
  const drawnHeight = sourceHeight * scale
  const offsetX = (width - drawnWidth) / 2
  const offsetY = (height - drawnHeight) / 2

  const points = corners.map(([x, y]) => ({
    x: offsetX + Number(x) * scale,
    y: offsetY + Number(y) * scale,
  }))

  const rootStyle = getComputedStyle(document.documentElement)
  const primary = rootStyle.getPropertyValue('--color-ui-primary-dark').trim() || '#184A32'

  context.save()
  context.lineWidth = 4
  context.strokeStyle = primary
  context.fillStyle = primary
  context.shadowColor = 'rgba(0,0,0,0.45)'
  context.shadowBlur = 8

  context.beginPath()
  context.moveTo(points[0].x, points[0].y)
  points.slice(1).forEach((point) => context.lineTo(point.x, point.y))
  context.closePath()
  context.stroke()

  points.forEach((point) => {
    context.beginPath()
    context.arc(point.x, point.y, 6, 0, Math.PI * 2)
    context.fill()
  })
  context.restore()
}

export default function LiveReceiptCornerGuide({
  videoRef,
  householdId,
  enabled,
  fit = 'cover',
}) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const video = videoRef?.current
    if (!canvas || !video || !enabled || !householdId) {
      const context = canvas?.getContext?.('2d')
      if (context && canvas) context.clearRect(0, 0, canvas.width, canvas.height)
      return undefined
    }

    let cancelled = false
    let timer = 0
    let busy = false
    const sampleCanvas = document.createElement('canvas')

    async function detect() {
      if (cancelled || busy) return
      if (!video.videoWidth || !video.videoHeight || video.readyState < 2) {
        timer = window.setTimeout(detect, 400)
        return
      }

      busy = true
      try {
        const maxWidth = 480
        const scale = Math.min(1, maxWidth / video.videoWidth)
        sampleCanvas.width = Math.max(1, Math.round(video.videoWidth * scale))
        sampleCanvas.height = Math.max(1, Math.round(video.videoHeight * scale))
        const sampleContext = sampleCanvas.getContext('2d')
        sampleContext?.drawImage(video, 0, 0, sampleCanvas.width, sampleCanvas.height)
        const blob = await new Promise((resolve) => sampleCanvas.toBlob(resolve, 'image/jpeg', 0.72))
        if (!blob || cancelled) return

        const form = new FormData()
        form.append('household_id', householdId)
        form.append('file', blob, 'live-camera-frame.jpg')
        const response = await fetch('/api/receipts/scanner/detect-live', {
          method: 'POST',
          credentials: 'include',
          body: form,
        })
        if (!response.ok || cancelled) return
        const result = await response.json().catch(() => ({}))
        if (!cancelled) drawGuide(canvas, video, result, fit)
      } catch {
        // Live guidance is optional: camera capture must remain usable if a
        // detection frame fails or the AI service is temporarily unavailable.
      } finally {
        busy = false
        if (!cancelled) timer = window.setTimeout(detect, 650)
      }
    }

    detect()
    const resizeObserver = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(() => drawGuide(canvas, video, null, fit))
      : null
    resizeObserver?.observe(video)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
      resizeObserver?.disconnect()
      const context = canvas.getContext('2d')
      context?.clearRect(0, 0, canvas.width, canvas.height)
    }
  }, [videoRef, householdId, enabled, fit])

  if (!enabled) return null
  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      data-testid="kassa-ai-live-corner-guide"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    />
  )
}
