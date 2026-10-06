const IDEAL_RECEIPT_WIDTH = 2560
const IDEAL_RECEIPT_HEIGHT = 1440
const SHARPNESS_SAMPLE_WIDTH = 240
const SHARPNESS_SETTLE_MS = 450
const SHARPNESS_FRAME_GAP_MS = 110
const SHARPNESS_FRAME_COUNT = 3
const MAX_AUTO_CAMERA_CANDIDATES = 5
const PREFERRED_CAMERA_STORAGE_KEY = 'inhuis.receipt-camera.preferred-device.v2'

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
  let score = device?.deviceId && device.deviceId === currentDeviceId ? 20 : 0
  if (/(back|rear|environment|achter|main|wide|1x)/i.test(label)) score += 40
  if (likelyFrontCamera(device)) score -= 200
  if (/(ultra.?wide|ultrawide|0[.,]5x|0[.,]6x)/i.test(label)) score -= 25
  if (/(telephoto|tele\b|zoom)/i.test(label)) score -= 15
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
    // Autofocus-capabilities verschillen per browser/toestel; camerabeeld blijft bruikbaar.
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

  const xStart = Math.max(1, Math.floor(width * 0.12))
  const xEnd = Math.min(width - 1, Math.ceil(width * 0.88))
  const yStart = Math.max(1, Math.floor(height * 0.12))
  const yEnd = Math.min(height - 1, Math.ceil(height * 0.88))
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

async function waitForVideoReady(video) {
  if (video.videoWidth > 0 && video.videoHeight > 0) return
  await new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      cleanup()
      reject(new Error('Camera gaf niet op tijd een meetbaar beeld.'))
    }, 1800)
    const cleanup = () => {
      window.clearTimeout(timer)
      video.removeEventListener('loadeddata', ready)
      video.removeEventListener('error', failed)
    }
    const ready = () => {
      cleanup()
      resolve()
    }
    const failed = () => {
      cleanup()
      reject(new Error('Camera kon niet voor scherpte worden gemeten.'))
    }
    video.addEventListener('loadeddata', ready, { once: true })
    video.addEventListener('error', failed, { once: true })
  })
}

async function measureStreamSharpness(stream) {
  const video = document.createElement('video')
  video.muted = true
  video.playsInline = true
  video.srcObject = stream
  await video.play()
  await waitForVideoReady(video)
  await wait(SHARPNESS_SETTLE_MS)

  const ratio = video.videoHeight / Math.max(1, video.videoWidth)
  const width = SHARPNESS_SAMPLE_WIDTH
  const height = Math.max(90, Math.round(width * ratio))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) return 0

  const scores = []
  for (let frame = 0; frame < SHARPNESS_FRAME_COUNT; frame += 1) {
    context.drawImage(video, 0, 0, width, height)
    const image = context.getImageData(0, 0, width, height)
    scores.push(calculateSharpnessScore(image.data, width, height))
    if (frame + 1 < SHARPNESS_FRAME_COUNT) await wait(SHARPNESS_FRAME_GAP_MS)
  }
  video.pause()
  video.srcObject = null
  scores.sort((left, right) => left - right)
  return scores[Math.floor(scores.length / 2)] || 0
}

function readPreferredCameraId() {
  try {
    return String(window.localStorage?.getItem(PREFERRED_CAMERA_STORAGE_KEY) || '')
  } catch {
    return ''
  }
}

function rememberPreferredCameraId(deviceId) {
  if (!deviceId) return
  try {
    window.localStorage?.setItem(PREFERRED_CAMERA_STORAGE_KEY, deviceId)
  } catch {
    // Opslag is optioneel; de automatische meting blijft per sessie bruikbaar.
  }
}

function streamFacingMode(stream) {
  const settings = stream?.getVideoTracks?.()[0]?.getSettings?.() || {}
  return String(settings.facingMode || '')
}

async function autoSelectSharpestCamera(devices, initialStream, initialDeviceId) {
  const ranked = rankReceiptCameras(devices, initialDeviceId)
  const usable = ranked.filter((device) => !likelyFrontCamera(device)).slice(0, MAX_AUTO_CAMERA_CANDIDATES)
  if (usable.length < 2) {
    return { stream: initialStream, activeDeviceId: initialDeviceId, scores: [] }
  }

  const storedId = readPreferredCameraId()
  if (storedId && usable.some((device) => device.deviceId === storedId)) {
    if (storedId === initialDeviceId) {
      return { stream: initialStream, activeDeviceId: initialDeviceId, scores: [] }
    }
    try {
      const storedStream = await requestReceiptStream(storedId)
      if (streamFacingMode(storedStream) !== 'user') {
        stopReceiptCameraStream(initialStream)
        return { stream: storedStream, activeDeviceId: storedId, scores: [] }
      }
      stopReceiptCameraStream(storedStream)
    } catch {
      // Een oude deviceId kan door browser/OS veranderen; meet dan opnieuw.
    }
  }

  const scores = []
  let currentStream = initialStream
  let currentId = initialDeviceId

  for (const device of usable) {
    let candidateStream = null
    const candidateId = String(device.deviceId || '')
    try {
      if (candidateId === initialDeviceId && currentStream) {
        candidateStream = currentStream
      } else {
        candidateStream = await requestReceiptStream(candidateId)
      }
      if (streamFacingMode(candidateStream) === 'user') {
        scores.push({ deviceId: candidateId, score: -1 })
      } else {
        const score = await measureStreamSharpness(candidateStream)
        scores.push({ deviceId: candidateId, score })
      }
    } catch {
      scores.push({ deviceId: candidateId, score: -1 })
    } finally {
      if (candidateStream && candidateStream !== currentStream) stopReceiptCameraStream(candidateStream)
    }
  }

  const best = scores
    .filter((entry) => entry.score >= 0)
    .sort((left, right) => right.score - left.score)[0]

  if (!best?.deviceId || best.deviceId === currentId) {
    if (best?.deviceId) rememberPreferredCameraId(best.deviceId)
    return { stream: currentStream, activeDeviceId: currentId, scores }
  }

  stopReceiptCameraStream(currentStream)
  currentStream = await requestReceiptStream(best.deviceId)
  currentId = String(currentStream.getVideoTracks?.()[0]?.getSettings?.().deviceId || best.deviceId)
  rememberPreferredCameraId(currentId)
  return { stream: currentStream, activeDeviceId: currentId, scores }
}

export async function openReceiptCamera({ deviceId = '' } = {}) {
  let stream = await requestReceiptStream(deviceId)
  let settings = stream.getVideoTracks?.()[0]?.getSettings?.() || {}
  let activeDeviceId = String(settings.deviceId || deviceId || '')

  let devices = []
  try {
    devices = await navigator.mediaDevices.enumerateDevices()
  } catch {
    return { stream, devices: [], activeDeviceId, sharpnessScores: [] }
  }

  if (deviceId) {
    rememberPreferredCameraId(activeDeviceId || deviceId)
    return {
      stream,
      devices: rankReceiptCameras(devices, activeDeviceId),
      activeDeviceId,
      sharpnessScores: [],
    }
  }

  try {
    const selected = await autoSelectSharpestCamera(devices, stream, activeDeviceId)
    stream = selected.stream
    activeDeviceId = selected.activeDeviceId
    return {
      stream,
      devices: rankReceiptCameras(devices, activeDeviceId),
      activeDeviceId,
      sharpnessScores: selected.scores,
    }
  } catch {
    return {
      stream,
      devices: rankReceiptCameras(devices, activeDeviceId),
      activeDeviceId,
      sharpnessScores: [],
    }
  }
}
