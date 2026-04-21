import { useCallback, useEffect, useRef, useState } from 'react'
import { createBarcodeReader, listBarcodeVideoDevices, mapBarcodeCameraErrorToUserMessage, openBarcodeCameraStream, startBarcodeDecoding } from './barcodeScanner'

function ensureScannerLogBuffer() {
  if (typeof window === 'undefined') return null
  if (!Array.isArray(window.__rezzervScannerLog)) window.__rezzervScannerLog = []
  return window.__rezzervScannerLog
}

function nextScannerSessionId() {
  if (typeof window === 'undefined') return `scan-${Date.now()}`
  window.__rezzervScannerSessionCounter = (window.__rezzervScannerSessionCounter || 0) + 1
  return `scan-${Date.now()}-${window.__rezzervScannerSessionCounter}`
}

export default function useBarcodeScanner({ onDetected = null, timeoutMs = 7000, screenContext = 'unknown' } = {}) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const readerRef = useRef(null)
  const controlsRef = useRef(null)
  const busyRef = useRef(false)
  const timeoutRef = useRef(null)
  const sessionIdRef = useRef('')

  const [isOpen, setIsOpen] = useState(false)
  const [cameraState, setCameraState] = useState({ status: 'idle', message: '' })
  const [cameraMeta, setCameraMeta] = useState({ deviceId: '', label: '', decodeAttempts: 0 })
  const [availableCameras, setAvailableCameras] = useState([])

  const logEvent = useCallback((event, payload = {}) => {
    const entry = {
      ts: new Date().toISOString(),
      sessionId: sessionIdRef.current || 'no-session',
      screen: screenContext,
      event,
      payload,
    }
    const buffer = ensureScannerLogBuffer()
    if (buffer) buffer.push(entry)
    console.info('[REZZERV_SCANNER]', entry)
    return entry
  }, [screenContext])

  const stopScanner = useCallback((preserveMessage = false, reason = 'unspecified') => {
    logEvent('SCANNER_STOP_REQUESTED', { preserveMessage, reason })
    busyRef.current = false
    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
    if (controlsRef.current?.stop) {
      try { controlsRef.current.stop() } catch {}
      controlsRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        logEvent('TRACK_STOP_CALLED', { label: track.label, readyState: track.readyState })
        track.stop()
      })
      streamRef.current = null
    }
    const video = videoRef.current
    if (video) {
      try { video.pause() } catch {}
      video.srcObject = null
    }
    setIsOpen(false)
    setCameraState((current) => (preserveMessage ? current : { status: 'idle', message: '' }))
    logEvent('SCANNER_STOP_COMPLETED', { preserveMessage, reason })
  }, [logEvent])

  const startScanner = useCallback(async (preferredDeviceId = '') => {
    sessionIdRef.current = nextScannerSessionId()
    logEvent('SCAN_CLICKED', { preferredDeviceId })
    stopScanner(false, 'restart-before-start')
    busyRef.current = false
    setCameraMeta({ deviceId: '', label: '', decodeAttempts: 0 })
    setCameraState({ status: 'loading', message: 'Camera openen…' })
    setIsOpen(true)

    if (!navigator.mediaDevices?.getUserMedia) {
      logEvent('GET_USER_MEDIA_ERROR', { message: 'Deze browser kan de apparaatcamera niet openen.' })
      setCameraState({ status: 'error', message: 'Deze browser kan de apparaatcamera niet openen.' })
      setIsOpen(false)
      return
    }

    try {
      logEvent('GET_USER_MEDIA_START', { preferredDeviceId })
      const { stream, activeDeviceId, activeLabel, trackSettings } = await openBarcodeCameraStream(preferredDeviceId, logEvent)
      streamRef.current = stream
      readerRef.current = readerRef.current || createBarcodeReader()
      const devices = await listBarcodeVideoDevices().catch(() => [])
      setAvailableCameras(devices)
      setCameraMeta({ deviceId: activeDeviceId || preferredDeviceId || '', label: activeLabel || '', decodeAttempts: 0 })
      logEvent('GET_USER_MEDIA_SUCCESS', { activeDeviceId, activeLabel, trackSettings })

      const video = videoRef.current
      logEvent('VIDEO_ELEMENT_FOUND', { found: Boolean(video) })
      if (!video) throw new Error('Cameraweergave kon niet worden gestart')
      video.srcObject = stream
      logEvent('STREAM_ATTACHED_TO_VIDEO', { hasSrcObject: Boolean(video.srcObject) })
      logEvent('VIDEO_PLAY_START')
      await video.play()
      logEvent('VIDEO_PLAY_SUCCESS', { paused: video.paused })

      timeoutRef.current = window.setTimeout(() => {
        logEvent('SCAN_TIMEOUT_REACHED', { timeoutMs })
        setCameraState({ status: 'not_found', message: 'Camera actief, maar nog geen barcode herkend. Houd de barcode dichterbij, vlakker en scherper in beeld of probeer handmatig invullen.' })
      }, timeoutMs)

      controlsRef.current = await startBarcodeDecoding({
        log: logEvent,
        video,
        reader: readerRef.current,
        onAttempt: () => {
          setCameraMeta((current) => {
            const nextAttempts = current.decodeAttempts + 1
            logEvent('DECODE_ATTEMPT', { attempts: nextAttempts })
            return { ...current, decodeAttempts: nextAttempts }
          })
        },
        onResult: async (result) => {
          if (busyRef.current) return
          const detectedBarcode = String(result?.getText?.() || result?.text || '').trim()
          const detectedFormat = String(result?.getBarcodeFormat?.() || result?.format || '').trim()
          if (!detectedBarcode) return
          busyRef.current = true
          if (timeoutRef.current) {
            window.clearTimeout(timeoutRef.current)
            timeoutRef.current = null
          }
          logEvent('DECODE_RESULT_FOUND', { text: detectedBarcode, format: detectedFormat })
          logEvent('DECODE_RESULT_TEXT', { text: detectedBarcode })
          logEvent('DECODE_RESULT_FORMAT', { format: detectedFormat })
          setCameraState({ status: 'found', message: 'Barcode herkend.' })
          stopScanner(true, 'decode-success')
          try {
            await onDetected?.(detectedBarcode, { logEvent, sessionId: sessionIdRef.current, screenContext })
            logEvent('SCAN_SESSION_END', { outcome: 'barcode-detected' })
          } finally {
            busyRef.current = false
          }
        },
        onNonFatalError: (error) => {
          if (busyRef.current) return
          logEvent('DECODE_NON_FATAL_ERROR', { errorName: error?.name, errorMessage: error?.message })
        },
        onFatalError: (error) => {
          logEvent('DECODER_START_ERROR', { errorName: error?.name, errorMessage: error?.message })
          stopScanner(false, 'fatal-decode-error')
          setCameraState({ status: 'error', message: mapBarcodeCameraErrorToUserMessage(error) })
        },
      })

      logEvent('DECODER_START', { activeDeviceId, activeLabel })
      setCameraState({ status: 'decoding', message: 'Camera actief. Barcode zoeken…' })
    } catch (error) {
      logEvent('SCANNER_START_ERROR', { errorName: error?.name, errorMessage: error?.message })
      stopScanner(false, 'start-error')
      setCameraState({ status: 'error', message: mapBarcodeCameraErrorToUserMessage(error) })
    }
  }, [logEvent, onDetected, screenContext, stopScanner, timeoutMs])

  const switchCamera = useCallback(async () => {
    const devices = availableCameras.length ? availableCameras : await listBarcodeVideoDevices().catch(() => [])
    setAvailableCameras(devices)
    if (devices.length < 2) return
    logEvent('CAMERA_SWITCH_REQUESTED', { currentDeviceId: cameraMeta.deviceId })
    const currentIndex = devices.findIndex((device) => device.deviceId === cameraMeta.deviceId)
    const nextDevice = devices[(currentIndex + 1 + devices.length) % devices.length]
    if (nextDevice?.deviceId) await startScanner(nextDevice.deviceId)
  }, [availableCameras, cameraMeta.deviceId, logEvent, startScanner])

  useEffect(() => () => stopScanner(false, 'component-unmount'), [stopScanner])

  return {
    videoRef,
    isOpen,
    cameraState,
    cameraMeta,
    availableCameras,
    startScanner,
    stopScanner,
    switchCamera,
  }
}
