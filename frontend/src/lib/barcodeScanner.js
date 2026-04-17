import { BrowserMultiFormatReader } from '@zxing/browser'
import { BarcodeFormat, DecodeHintType } from '@zxing/library'

const ZXING_NON_FATAL_ERRORS = new Set(['NotFoundException', 'ChecksumException', 'FormatException'])
const RETAIL_BARCODE_FORMATS = [
  BarcodeFormat.EAN_13,
  BarcodeFormat.EAN_8,
  BarcodeFormat.UPC_A,
  BarcodeFormat.UPC_E,
  BarcodeFormat.CODE_128,
]

const SCAN_HINTS = new Map()
SCAN_HINTS.set(DecodeHintType.POSSIBLE_FORMATS, RETAIL_BARCODE_FORMATS)
SCAN_HINTS.set(DecodeHintType.TRY_HARDER, true)

const NATIVE_BARCODE_FORMATS = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128']

export function isNonFatalBarcodeScanError(error) {
  const name = String(error?.name || '').trim()
  const message = String(error?.message || error || '').trim().toLowerCase()
  if (ZXING_NON_FATAL_ERRORS.has(name)) return true
  if (!message) return false
  return (
    message.includes('no multiformat readers were able to detect the code') ||
    message.includes('no barcode found') ||
    message.includes('no code detected') ||
    message.includes('not found')
  )
}

export function mapBarcodeCameraErrorToUserMessage(error) {
  const rawMessage = String(error?.message || error || '').trim()
  const normalized = rawMessage.toLowerCase()

  if (!rawMessage) return 'Camera voor barcode scannen kon niet worden gestart. Probeer het opnieuw of vul de barcode handmatig in.'
  if (normalized.includes('failed to allocate videosource') || normalized.includes('could not start video source') || normalized.includes('video source') || normalized.includes('videosource') || normalized.includes('notreadableerror') || normalized.includes('trackstarterror') || normalized.includes('device in use')) {
    return 'Camera voor barcode scannen kon niet worden gestart met de huidige camera-instellingen. Probeer het opnieuw of kies een andere camera.'
  }
  if (normalized.includes('notallowederror') || normalized.includes('permission denied') || normalized.includes('permission dismissed') || normalized.includes('permission')) {
    return 'Rezzerv heeft nog geen toegang tot je camera. Geef cameratoegang en probeer het opnieuw.'
  }
  if (normalized.includes('notfounderror') || normalized.includes('devices not found') || normalized.includes('requested device not found') || normalized.includes('camera not found')) {
    return 'Er is geen bruikbare camera gevonden voor barcode scannen op dit apparaat.'
  }
  if (normalized.includes('overconstrainederror') || normalized.includes('constraint')) {
    return 'De gekozen camera-instellingen worden niet ondersteund op dit apparaat. Rezzerv probeert daarom een eenvoudigere camera-instelling.'
  }
  if (normalized.includes('securityerror') || normalized.includes('insecure context')) {
    return 'Barcode scannen werkt alleen in een veilige verbinding. Open Rezzerv via https of localhost en probeer het opnieuw.'
  }
  if (normalized.includes('aborterror')) return 'Het openen van de camera is onderbroken. Probeer het opnieuw.'
  return 'Camera voor barcode scannen kon niet worden gestart. Probeer het opnieuw of vul de barcode handmatig in.'
}

function isMobileBrowser() {
  const userAgent = String(window?.navigator?.userAgent || '').toLowerCase()
  return /android|iphone|ipad|ipod|mobile/.test(userAgent)
}

function scoreDeviceLabel(label = '') {
  const normalized = String(label || '').toLowerCase()
  let score = 0
  if (/(back|rear|environment|world)/.test(normalized)) score += 100
  if (/(external|usb|hd)/.test(normalized)) score += 25
  if (/(front|user|facetime|integrated)/.test(normalized)) score -= 50
  return score
}

function buildScanVideoConstraints(extra = {}) {
  return {
    width: { ideal: 1920 },
    height: { ideal: 1080 },
    aspectRatio: { ideal: 1.777777778 },
    frameRate: { ideal: 24, min: 10 },
    ...extra,
  }
}

export async function listBarcodeVideoDevices() {
  if (!navigator?.mediaDevices?.enumerateDevices) return []
  const devices = await navigator.mediaDevices.enumerateDevices()
  return devices.filter((device) => device.kind === 'videoinput')
}

async function applyTrackOptimizations(videoTrack) {
  if (!videoTrack?.getCapabilities || !videoTrack?.applyConstraints) return null
  const capabilities = videoTrack.getCapabilities() || {}
  const advanced = []
  if (Array.isArray(capabilities.focusMode)) {
    if (capabilities.focusMode.includes('continuous')) advanced.push({ focusMode: 'continuous' })
    else if (capabilities.focusMode.includes('single-shot')) advanced.push({ focusMode: 'single-shot' })
  }
  if (Array.isArray(capabilities.exposureMode) && capabilities.exposureMode.includes('continuous')) {
    advanced.push({ exposureMode: 'continuous' })
  }
  if (typeof capabilities.zoom?.max === 'number' && capabilities.zoom.max >= 1.5) {
    advanced.push({ zoom: Math.min(2, capabilities.zoom.max) })
  }
  if (!advanced.length) return capabilities
  try {
    await videoTrack.applyConstraints({ advanced })
  } catch (error) {
    console.info('Barcode scanner kon optionele trackoptimalisaties niet toepassen', { error })
  }
  return capabilities
}

export async function openBarcodeCameraStream(preferredDeviceId = '', log = null) {
  const mobile = isMobileBrowser()
  const availableDevices = await listBarcodeVideoDevices().catch(() => [])
  const prioritizedDevices = [...availableDevices].sort((a, b) => scoreDeviceLabel(b.label) - scoreDeviceLabel(a.label))
  const attempts = []
  const seenAttemptKeys = new Set()

  const pushAttempt = (constraints) => {
    const key = JSON.stringify(constraints)
    if (seenAttemptKeys.has(key)) return
    seenAttemptKeys.add(key)
    attempts.push(constraints)
  }

  if (preferredDeviceId) {
    pushAttempt({ audio: false, video: buildScanVideoConstraints({ deviceId: { exact: preferredDeviceId } }) })
  }

  prioritizedDevices.forEach((device) => {
    if (device?.deviceId) {
      pushAttempt({ audio: false, video: buildScanVideoConstraints({ deviceId: { exact: device.deviceId } }) })
    }
  })

  if (mobile) {
    pushAttempt({ audio: false, video: buildScanVideoConstraints({ facingMode: { exact: 'environment' } }) })
    pushAttempt({ audio: false, video: buildScanVideoConstraints({ facingMode: { ideal: 'environment' } }) })
  } else {
    pushAttempt({ audio: false, video: buildScanVideoConstraints() })
  }

  pushAttempt({ audio: false, video: { width: { ideal: 1280 }, height: { ideal: 720 } } })
  pushAttempt({ audio: false, video: { width: { ideal: 640 }, height: { ideal: 480 } } })
  pushAttempt({ audio: false, video: true })

  let lastError = null
  for (const constraints of attempts) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      const videoTrack = stream?.getVideoTracks?.()?.[0]
      if (videoTrack) {
        const capabilities = await applyTrackOptimizations(videoTrack)
        const trackSettings = videoTrack.getSettings?.() || {}
        const activeDeviceId = trackSettings.deviceId || preferredDeviceId || ''
        const activeLabel = videoTrack.label || prioritizedDevices.find((device) => device.deviceId === activeDeviceId)?.label || ''
        log?.('CAMERA_TRACK_ACTIVE', { activeDeviceId, activeLabel, trackSettings, constraints })
        console.info('Barcode scanner camera actief', { activeDeviceId, activeLabel, trackSettings, capabilities, constraints })
        return { stream, activeDeviceId, activeLabel, trackSettings, capabilities, devices: availableDevices }
      }
      if (stream) stream.getTracks().forEach((track) => track.stop())
    } catch (error) {
      lastError = error
      log?.('CAMERA_START_ATTEMPT_FAILED', { constraints, errorName: error?.name, errorMessage: error?.message })
      console.warn('Barcode scanner camera startpoging mislukt', { constraints, error })
    }
  }

  throw lastError || new Error('Camera kon niet worden gestart')
}

export function createBarcodeReader() {
  return new BrowserMultiFormatReader(SCAN_HINTS, {
    delayBetweenScanAttempts: 120,
    delayBetweenScanSuccess: 500,
    tryPlayVideoTimeout: 5000,
  })
}

async function createNativeBarcodeDetector() {
  if (typeof window === 'undefined' || typeof window.BarcodeDetector === 'undefined') return null
  try {
    const supported = typeof window.BarcodeDetector.getSupportedFormats === 'function'
      ? await window.BarcodeDetector.getSupportedFormats()
      : []
    const formats = NATIVE_BARCODE_FORMATS.filter((format) => !supported.length || supported.includes(format))
    if (!formats.length) return null
    return new window.BarcodeDetector({ formats })
  } catch (error) {
    console.info('Native BarcodeDetector niet beschikbaar voor Rezzerv scanner', { error })
    return null
  }
}

function waitForVideoReady(video, log = null) {
  if (!video) return Promise.reject(new Error('Cameraweergave kon niet worden gestart'))
  if (video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) {
    log?.('VIDEO_METADATA_LOADED', { readyState: video.readyState, videoWidth: video.videoWidth, videoHeight: video.videoHeight })
    return Promise.resolve()
  }
  return new Promise((resolve, reject) => {
    let done = false
    const cleanup = () => {
      video.removeEventListener('loadedmetadata', handleReady)
      video.removeEventListener('loadeddata', handleReady)
      video.removeEventListener('canplay', handleReady)
      window.clearTimeout(timer)
    }
    const handleReady = () => {
      if (done) return
      if (video.readyState < 2 || video.videoWidth <= 0 || video.videoHeight <= 0) return
      done = true
      cleanup()
      log?.('VIDEO_METADATA_LOADED', { readyState: video.readyState, videoWidth: video.videoWidth, videoHeight: video.videoHeight })
      resolve()
    }
    const timer = window.setTimeout(() => {
      if (done) return
      done = true
      cleanup()
      reject(new Error('Cameraweergave bleef leeg na het starten van de stream'))
    }, 4000)
    video.addEventListener('loadedmetadata', handleReady)
    video.addEventListener('loadeddata', handleReady)
    video.addEventListener('canplay', handleReady)
  })
}

export async function startBarcodeDecoding({
  video,
  reader,
  onAttempt,
  onResult,
  onNonFatalError,
  onFatalError,
  log = null,
}) {
  if (!video) throw new Error('Cameraweergave kon niet worden gestart')
  if (!reader) throw new Error('Barcode reader ontbreekt')

  await waitForVideoReady(video, log)

  const nativeDetector = await createNativeBarcodeDetector()
  log?.('VIDEO_FIRST_FRAME_CONFIRMED', { readyState: video.readyState, videoWidth: video.videoWidth, videoHeight: video.videoHeight })

  if (nativeDetector) {
    let stopped = false
    let rafId = 0
    let timeoutId = 0

    const stop = () => {
      stopped = true
      if (rafId) window.cancelAnimationFrame(rafId)
      if (timeoutId) window.clearTimeout(timeoutId)
    }

    const loop = async () => {
      if (stopped) return
      if (video.readyState < 2 || video.videoWidth <= 0 || video.videoHeight <= 0) {
        rafId = window.requestAnimationFrame(loop)
        return
      }
      try {
        onAttempt?.()
        const detections = await nativeDetector.detect(video)
        const detection = Array.isArray(detections) ? detections.find((item) => item?.rawValue) : null
        if (detection?.rawValue) {
          stop()
          onResult?.({ text: detection.rawValue, rawValue: detection.rawValue, format: detection.format })
          return
        }
      } catch (error) {
        if (!stopped) {
          console.info('Native BarcodeDetector scanpoging zonder resultaat', { error })
          onNonFatalError?.(error)
        }
      }
      timeoutId = window.setTimeout(() => {
        rafId = window.requestAnimationFrame(loop)
      }, 140)
    }

    rafId = window.requestAnimationFrame(loop)
    return { stop }
  }

  const controls = await reader.decodeFromVideoElement(video, (result, error) => {
    if (result) {
      onResult?.(result)
      return
    }
    onAttempt?.()
    if (!error) return
    if (isNonFatalBarcodeScanError(error)) {
      onNonFatalError?.(error)
      return
    }
    onFatalError?.(error)
  })

  return {
    stop: () => {
      try { controls?.stop?.() } catch {}
      try { reader.reset?.() } catch {}
    },
  }
}

