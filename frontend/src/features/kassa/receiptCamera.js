const IDEAL_RECEIPT_WIDTH = 2560
const IDEAL_RECEIPT_HEIGHT = 1440
const SHARPNESS_SAMPLE_WIDTH = 320
const SHARPNESS_SETTLE_MS = 1100
const SHARPNESS_FRAME_GAP_MS = 140
const SHARPNESS_FRAME_COUNT = 5
const MAX_AUTO_CAMERA_CANDIDATES = 5

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function normalizedLabel(device) {
  return String(device?.label || '').trim().toLowerCase()
}

function likelyFrontCamera(device) {
  return /(front|user|selfie|voor)/i.test(normalizedLabel(device))
}

function cameraHeuristicScore(device, currentDeviceId = '') {
  const label = normalizedLabel(device)
  let score = device?.deviceId && device.deviceId === currentDeviceId ? 10 : 0
  if (/(back|rear|environment|achter|main|wide|1x)/i.test(label)) score += 30
  if (likelyFrontCamera(device)) score -= 200
  return score
}

export function rankReceiptCameras(devices, currentDeviceId = '') {
  return (Array.isArray(devices) ? devices : [])
    .filter((device) => device?.kind === 'videoinput' && device?.deviceId)
    .map((device, index) => ({ device, index, score: cameraHeuristicScore(device, currentDeviceId) }))
    .sort((left, right) => right.score - left.score || left.index - right.index)
    .map(({ device }) => device)
}

export function stopReceiptCameraStream(stream) {
  stream?.getTracks?.().forEach((track) => track.stop())
}

async function applyReceiptFocus(track) {
  if (!track?.applyConstraints || !track?.getCapabilities) return
  try {
    const capabilities = track.getCapabilities() || {}
    const focusModes = Array.isArray(capabilities.focusMode) ? capabilities.focusMode : []
    if (focusModes.includes('continuous')) {
      await track.applyConstraints({ advanced: [{ focusMode: 'continuous' }] })
    }
  } catch {
    // Autofocus-capabilities verschillen per browser/toestel.
  }
}

async function requestReceiptStream(deviceId = '') {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('Camera is niet rechtstreeks beschikbaar.')
  }
  const video = deviceId
    ? {
        deviceId: { exact: deviceId },
        width: { ideal: IDEAL_RECEIPT_WIDTH },
        height: { ideal: IDEAL_RECEIPT_HEIGHT },
      }
    : {
        facingMode: { ideal: 'environment' },
        width: { ideal: IDEAL_RECEIPT_WIDTH },
        height: { ideal: IDEAL_RECEIPT_HEIGHT },
      }
  const stream = await navigator.mediaDevices.getUserMedia({ video, audio: false })
  await applyReceiptFocus(stream.getVideoTracks?.()[0])
  return stream
}

export function calculateSharpnessScore(rgba, width, height) {
  if (!rgba || width < 3 || height < 3) return 0
  const gray = new Float32Array(width * height)
  for (let index = 0, pixel = 0; index < gray.length; index += 1, pixel += 4) {
    gray[index] = (rgba[pixel] * 0.299) + (rgba[pixel + 1] * 0.587) + (rgba[pixel + 2] * 0.114)
  }

  const xStart = Math.max(1, Math.floor(width * 0.15))
  const xEnd = Math.min(width - 1, Math.ceil(width * 0.85))
  const yStart = Math.max(1, Math.floor(height * 0.15))
  const yEnd = Math.min(height - 1, Math.ceil(height * 0.85))
  let sum = 0
  let sumSquares = 0
  let count = 0

  for (let y = yStart; y < yEnd; y += 1) {
    const row = y * width
    for (let x = xStart; x < xEnd; x += 1) {
      const i = row + x
      const laplacian = (4 * gray[i]) - gray[i - 1] - gray[i + 1] - gray[i - width] - gray[i + width]
      sum += laplacian
      sumSquares += laplacian * laplacian
      count += 1
    }
  }

  if (!count) return 0
  const mean = sum / count
  return Math.max(0, (sumSquares / count) - (mean * mean))
}

async function attachStreamToPreview(previewVideo, stream) {
  if (!previewVideo) throw new Error('Cameravoorbeeld ontbreekt.')
  previewVideo.srcObject = stream
  await previewVideo.play().catch(() => {})
  if (previewVideo.videoWidth > 0 && previewVideo.videoHeight > 0) return

  await new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      cleanup()
      reject(new Error('Camera gaf niet op tijd beeld.'))
    }, 2500)
    const cleanup = () => {
      window.clearTimeout(timer)
      previewVideo.removeEventListener('loadedmetadata', ready)
      previewVideo.removeEventListener('loadeddata', ready)
      previewVideo.removeEventListener('error', failed)
    }
    const ready = () => {
      cleanup()
      resolve()
    }
    const failed = () => {
      cleanup()
      reject(new Error('Camera kon niet worden weergegeven.'))
    }
    previewVideo.addEventListener('loadedmetadata', ready, { once: true })
    previewVideo.addEventListener('loadeddata', ready, { once: true })
    previewVideo.addEventListener('error', failed, { once: true })
  })
}

async function measureVisiblePreviewSharpness(previewVideo) {
  await wait(SHARPNESS_SETTLE_MS)
  const ratio = previewVideo.videoHeight / Math.max(1, previewVideo.videoWidth)
  const width = SHARPNESS_SAMPLE_WIDTH
  const height = Math.max(120, Math.round(width * ratio))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) return 0

  const scores = []
  for (let frame = 0; frame < SHARPNESS_FRAME_COUNT; frame += 1) {
    context.drawImage(previewVideo, 0, 0, width, height)
    const image = context.getImageData(0, 0, width, height)
    scores.push(calculateSharpnessScore(image.data, width, height))
    if (frame + 1 < SHARPNESS_FRAME_COUNT) await wait(SHARPNESS_FRAME_GAP_MS)
  }

  scores.sort((left, right) => left - right)
  return scores[Math.floor(scores.length / 2)] || 0
}

function streamFacingMode(stream) {
  return String(stream?.getVideoTracks?.()[0]?.getSettings?.().facingMode || '')
}

async function scoreCameraOnVisiblePreview(deviceId, previewVideo) {
  const stream = await requestReceiptStream(deviceId)
  try {
    if (streamFacingMode(stream) === 'user') return { score: -1, stream: null }
    await attachStreamToPreview(previewVideo, stream)
    const score = await measureVisiblePreviewSharpness(previewVideo)
    return { score, stream }
  } catch (error) {
    stopReceiptCameraStream(stream)
    throw error
  }
}

async function autoSelectSharpestCamera(devices, initialStream, initialDeviceId, previewVideo) {
  const ranked = rankReceiptCameras(devices, initialDeviceId)
  const usable = ranked.filter((device) => !likelyFrontCamera(device)).slice(0, MAX_AUTO_CAMERA_CANDIDATES)
  if (usable.length < 2 || !previewVideo) {
    await attachStreamToPreview(previewVideo, initialStream)
    return { stream: initialStream, activeDeviceId: initialDeviceId, scores: [] }
  }

  stopReceiptCameraStream(initialStream)

  const scores = []
  let best = null

  for (const device of usable) {
    const candidateId = String(device.deviceId || '')
    try {
      const result = await scoreCameraOnVisiblePreview(candidateId, previewVideo)
      scores.push({ deviceId: candidateId, score: result.score })
      if (result.stream && (!best || result.score > best.score)) {
        if (best?.stream) stopReceiptCameraStream(best.stream)
        best = { deviceId: candidateId, score: result.score, stream: result.stream }
      } else if (result.stream) {
        stopReceiptCameraStream(result.stream)
      }
    } catch {
      scores.push({ deviceId: candidateId, score: -1 })
    }
  }

  if (!best?.stream) {
    const fallback = await requestReceiptStream(initialDeviceId)
    await attachStreamToPreview(previewVideo, fallback)
    return { stream: fallback, activeDeviceId: initialDeviceId, scores }
  }

  await attachStreamToPreview(previewVideo, best.stream)
  const actualId = String(best.stream.getVideoTracks?.()[0]?.getSettings?.().deviceId || best.deviceId)
  return { stream: best.stream, activeDeviceId: actualId, scores }
}

export async function openReceiptCamera({ deviceId = '', previewVideo = null } = {}) {
  let stream = await requestReceiptStream(deviceId)
  const settings = stream.getVideoTracks?.()[0]?.getSettings?.() || {}
  let activeDeviceId = String(settings.deviceId || deviceId || '')

  let devices = []
  try {
    devices = await navigator.mediaDevices.enumerateDevices()
  } catch {
    if (previewVideo) await attachStreamToPreview(previewVideo, stream)
    return { stream, devices: [], activeDeviceId, sharpnessScores: [] }
  }

  if (deviceId) {
    if (previewVideo) await attachStreamToPreview(previewVideo, stream)
    return {
      stream,
      devices: rankReceiptCameras(devices, activeDeviceId),
      activeDeviceId,
      sharpnessScores: [],
    }
  }

  try {
    const selected = await autoSelectSharpestCamera(devices, stream, activeDeviceId, previewVideo)
    stream = selected.stream
    activeDeviceId = selected.activeDeviceId
    return {
      stream,
      devices: rankReceiptCameras(devices, activeDeviceId),
      activeDeviceId,
      sharpnessScores: selected.scores,
    }
  } catch {
    if (previewVideo) await attachStreamToPreview(previewVideo, stream).catch(() => {})
    return {
      stream,
      devices: rankReceiptCameras(devices, activeDeviceId),
      activeDeviceId,
      sharpnessScores: [],
    }
  }
}
