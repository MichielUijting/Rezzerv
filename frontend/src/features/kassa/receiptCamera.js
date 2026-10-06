const IDEAL_RECEIPT_WIDTH = 2560
const IDEAL_RECEIPT_HEIGHT = 1440

function normalizedLabel(device) {
  return String(device?.label || '').trim().toLowerCase()
}

function capabilitiesFor(device) {
  try {
    return typeof device?.getCapabilities === 'function' ? (device.getCapabilities() || {}) : {}
  } catch {
    return {}
  }
}

function cameraScore(device, currentDeviceId = '') {
  const label = normalizedLabel(device)
  const capabilities = capabilitiesFor(device)
  const facingModes = Array.isArray(capabilities.facingMode) ? capabilities.facingMode : []
  let score = device?.deviceId && device.deviceId === currentDeviceId ? 30 : 0

  if (facingModes.includes('environment')) score += 80
  if (facingModes.includes('user')) score -= 180

  if (/(back|rear|environment|achter|main|wide|1x)/i.test(label)) score += 55
  if (/(front|user|selfie|voor)/i.test(label)) score -= 180
  if (/(ultra.?wide|ultrawide|0[.,]5x|0[.,]6x)/i.test(label)) score -= 70
  if (/(telephoto|tele\b|zoom)/i.test(label)) score -= 45

  const maxWidth = Number(capabilities?.width?.max || 0)
  if (Number.isFinite(maxWidth) && maxWidth > 0) score += Math.min(30, maxWidth / 200)

  const focusModes = Array.isArray(capabilities.focusMode) ? capabilities.focusMode : []
  if (focusModes.includes('continuous')) score += 25
  return score
}

export function rankReceiptCameras(devices, currentDeviceId = '') {
  return (Array.isArray(devices) ? devices : [])
    .filter((device) => device?.kind === 'videoinput' && device?.deviceId)
    .map((device, index) => ({ device, index, score: cameraScore(device, currentDeviceId) }))
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

export async function openReceiptCamera({ deviceId = '' } = {}) {
  let stream = await requestReceiptStream(deviceId)
  let track = stream.getVideoTracks?.()[0]
  let settings = track?.getSettings?.() || {}
  let activeDeviceId = String(settings.deviceId || deviceId || '')

  let devices = []
  try {
    devices = await navigator.mediaDevices.enumerateDevices()
  } catch {
    return { stream, devices: [], activeDeviceId }
  }

  const ranked = rankReceiptCameras(devices, activeDeviceId)
  if (!deviceId && ranked.length > 1) {
    const bestDeviceId = String(ranked[0]?.deviceId || '')
    if (bestDeviceId && bestDeviceId !== activeDeviceId) {
      try {
        const betterStream = await requestReceiptStream(bestDeviceId)
        stopReceiptCameraStream(stream)
        stream = betterStream
        track = stream.getVideoTracks?.()[0]
        settings = track?.getSettings?.() || {}
        activeDeviceId = String(settings.deviceId || bestDeviceId)
      } catch {
        // De browser kan een opgesomde lens alsnog weigeren; behoud de werkende environment-camera.
      }
    }
  }

  return {
    stream,
    devices: rankReceiptCameras(devices, activeDeviceId),
    activeDeviceId,
  }
}
