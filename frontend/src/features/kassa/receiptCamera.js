const IDEAL_RECEIPT_WIDTH = 3840
const IDEAL_RECEIPT_HEIGHT = 2160
const MAX_AUTO_CAMERA_CANDIDATES = 6

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

function streamFacingMode(stream) {
  return String(stream?.getVideoTracks?.()[0]?.getSettings?.().facingMode || '')
}

export function cameraPixelCapacity(track) {
  if (!track) return 0
  let width = 0
  let height = 0

  try {
    const capabilities = track.getCapabilities?.() || {}
    width = Number(capabilities?.width?.max || 0)
    height = Number(capabilities?.height?.max || 0)
  } catch {
    // Gebruik hieronder de werkelijk geopende resolutie als fallback.
  }

  if (!(width > 0 && height > 0)) {
    const settings = track.getSettings?.() || {}
    width = Number(settings.width || 0)
    height = Number(settings.height || 0)
  }

  return width > 0 && height > 0 ? width * height : 0
}

async function inspectCameraResolution(deviceId) {
  const stream = await requestReceiptStream(deviceId)
  try {
    const track = stream.getVideoTracks?.()[0]
    if (streamFacingMode(stream) === 'user') {
      return { deviceId, pixels: -1, width: 0, height: 0 }
    }

    const capabilities = track?.getCapabilities?.() || {}
    const settings = track?.getSettings?.() || {}
    const width = Number(capabilities?.width?.max || settings.width || 0)
    const height = Number(capabilities?.height?.max || settings.height || 0)
    return {
      deviceId,
      pixels: cameraPixelCapacity(track),
      width,
      height,
    }
  } finally {
    stopReceiptCameraStream(stream)
  }
}

async function autoSelectHighestResolutionCamera(devices, initialStream, initialDeviceId) {
  const ranked = rankReceiptCameras(devices, initialDeviceId)
  const usable = ranked
    .filter((device) => !likelyFrontCamera(device))
    .slice(0, MAX_AUTO_CAMERA_CANDIDATES)

  if (usable.length < 2) {
    return { stream: initialStream, activeDeviceId: initialDeviceId, resolutions: [] }
  }

  const resolutions = []
  for (const device of usable) {
    try {
      resolutions.push(await inspectCameraResolution(String(device.deviceId || '')))
    } catch {
      resolutions.push({ deviceId: String(device.deviceId || ''), pixels: -1, width: 0, height: 0 })
    }
  }

  const best = resolutions
    .filter((entry) => entry.pixels >= 0)
    .sort((left, right) => right.pixels - left.pixels)[0]

  if (!best?.deviceId || best.deviceId === initialDeviceId) {
    return { stream: initialStream, activeDeviceId: initialDeviceId, resolutions }
  }

  stopReceiptCameraStream(initialStream)
  const bestStream = await requestReceiptStream(best.deviceId)
  const actualId = String(bestStream.getVideoTracks?.()[0]?.getSettings?.().deviceId || best.deviceId)
  return { stream: bestStream, activeDeviceId: actualId, resolutions }
}

export async function openReceiptCamera({ deviceId = '' } = {}) {
  let stream = await requestReceiptStream(deviceId)
  const settings = stream.getVideoTracks?.()[0]?.getSettings?.() || {}
  let activeDeviceId = String(settings.deviceId || deviceId || '')

  let devices = []
  try {
    devices = await navigator.mediaDevices.enumerateDevices()
  } catch {
    return { stream, devices: [], activeDeviceId, cameraResolutions: [] }
  }

  if (deviceId) {
    return {
      stream,
      devices: rankReceiptCameras(devices, activeDeviceId),
      activeDeviceId,
      cameraResolutions: [],
    }
  }

  try {
    const selected = await autoSelectHighestResolutionCamera(devices, stream, activeDeviceId)
    stream = selected.stream
    activeDeviceId = selected.activeDeviceId
    return {
      stream,
      devices: rankReceiptCameras(devices, activeDeviceId),
      activeDeviceId,
      cameraResolutions: selected.resolutions,
    }
  } catch {
    return {
      stream,
      devices: rankReceiptCameras(devices, activeDeviceId),
      activeDeviceId,
      cameraResolutions: [],
    }
  }
}
