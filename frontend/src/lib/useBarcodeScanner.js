import { useCallback, useEffect, useRef, useState } from 'react'
import { createBarcodeReader, listBarcodeVideoDevices, mapBarcodeCameraErrorToUserMessage, openBarcodeCameraStream, startBarcodeDecoding } from './barcodeScanner'
import { diagnoseBarcodeCameraFailure } from './barcodeCameraRecovery.js'

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
  const autoCameraAttemptedRef = useRef(new Set())
  const startScannerRef = useRef(null)
  const requestTokenRef = useRef(0)

  const [isOpen, setIsOpen] = useState(false)
  const [cameraState, setCameraState] = useState({ status: 'idle', message: '' })
  const [cameraErrorRevision, setCameraErrorRevision] = useState(0)
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
    requestTokenRef.current += 1
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

  const startScanner = useCallback(async (preferredDeviceId = '', options = {}) => {
    const compatibilityMode = options?.compatibilityMode === true
    sessionIdRef.current = nextScannerSessionId()
    if (!preferredDeviceId) autoCameraAttemptedRef.current = new Set()
    logEvent('SCAN_CLICKED', { preferredDeviceId, compatibilityMode })
    stopScanner(false, 'restart-before-start')
    const requestToken = requestTokenRef.current
    busyRef.current = false
    setCameraMeta({ deviceId: '', label: '', decodeAttempts: 0 })
    setCameraState({ status: 'loading', message: compatibilityMode
      ? 'Camera met tijdelijke eenvoudige instellingen openen…' : 'Camera openen…' })
    setIsOpen(true)

    if (!navigator.mediaDevices?.getUserMedia) {
      logEvent('GET_USER_MEDIA_ERROR', { message: 'Live camera is in deze browser niet beschikbaar.' })
      setCameraErrorRevision((revision) => revision + 1)
      const recovery = diagnoseBarcodeCameraFailure({ name: 'SecurityError' }, {
        secureContext: typeof window === 'undefined' ? false : window.isSecureContext !== false,
        mediaSupported: false,
        userAgent: navigator.userAgent || '',
      })
      setCameraState({ status: 'error', message: recovery.message, recovery })
      setIsOpen(false)
      return
    }

    try {
      logEvent('GET_USER_MEDIA_START', { preferredDeviceId, compatibilityMode })
      const { stream, activeDeviceId, activeLabel, trackSettings } = await openBarcodeCameraStream(
        preferredDeviceId, logEvent, { compatibilityMode },
      )
      if (requestToken !== requestTokenRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      streamRef.current = stream
      readerRef.current = readerRef.current || createBarcodeReader()
      const devices = await listBarcodeVideoDevices().catch(() => [])
      setAvailableCameras(devices)
      const resolvedActiveDeviceId = activeDeviceId || preferredDeviceId || ''
      if (resolvedActiveDeviceId) autoCameraAttemptedRef.current.add(resolvedActiveDeviceId)
      setCameraMeta({ deviceId: resolvedActiveDeviceId, label: activeLabel || '', decodeAttempts: 0 })
      logEvent('GET_USER_MEDIA_SUCCESS', { activeDeviceId, activeLabel, trackSettings })

      // A cached browser permission can resolve before React has rendered
      // the <video> for the newly opened scanner dialog.
      if (!videoRef.current) await new Promise((resolve) => window.requestAnimationFrame(resolve))
      if (requestToken !== requestTokenRef.current) return
      const video = videoRef.current
      logEvent('VIDEO_ELEMENT_FOUND', { found: Boolean(video) })
      if (!video) throw new Error('Cameraweergave kon niet worden gestart')
      video.srcObject = stream
      logEvent('STREAM_ATTACHED_TO_VIDEO', { hasSrcObject: Boolean(video.srcObject) })
      logEvent('VIDEO_PLAY_START')
      await video.play()
      logEvent('VIDEO_PLAY_SUCCESS', { paused: video.paused })

      // A live camera should not be obscured by a no-result warning in ED2.
      // timeoutMs=0 opts out; the default 7s behavior remains for other callers.
      if (timeoutMs > 0) timeoutRef.current = window.setTimeout(async () => {
        logEvent('SCAN_TIMEOUT_REACHED', { timeoutMs })
        const cameras = devices.length ? devices : await listBarcodeVideoDevices().catch(() => [])
        const currentDeviceId = activeDeviceId || preferredDeviceId || ''
        const alternative = cameras.find((device) => device?.deviceId && device.deviceId !== currentDeviceId && !autoCameraAttemptedRef.current.has(device.deviceId))
        if (alternative?.deviceId) {
          autoCameraAttemptedRef.current.add(alternative.deviceId)
          logEvent('AUTO_CAMERA_SWITCH', { fromDeviceId: currentDeviceId, toDeviceId: alternative.deviceId, toLabel: alternative.label || '' })
          setCameraState({ status: 'loading', message: 'Nog geen barcode herkend. Inhuis probeert automatisch een andere camera…' })
          await startScannerRef.current?.(alternative.deviceId)
          return
        }
        setCameraState({ status: 'not_found', message: 'Camera actief, maar nog geen barcode herkend. Houd de barcode dichterbij, vlakker en scherper in beeld of vul de barcode handmatig in.' })
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
          setCameraErrorRevision((revision) => revision + 1)
      setCameraState({ status: 'error', message: mapBarcodeCameraErrorToUserMessage(error) })
        },
      })

      logEvent('DECODER_START', { activeDeviceId, activeLabel })
      setCameraState({ status: 'decoding', message: compatibilityMode
        ? 'Camera actief met tijdelijke instellingen. Barcode zoeken…'
        : 'Camera actief. Barcode zoeken…' })
    } catch (error) {
      if (requestToken !== requestTokenRef.current) return
      logEvent('SCANNER_START_ERROR', { errorName: error?.name, errorMessage: error?.message })
      stopScanner(false, 'start-error')
      const recovery = diagnoseBarcodeCameraFailure(error, {
        secureContext: typeof window === 'undefined' ? false : window.isSecureContext !== false,
        mediaSupported: Boolean(navigator.mediaDevices?.getUserMedia),
        userAgent: navigator.userAgent || '',
      })
      setAvailableCameras(await listBarcodeVideoDevices().catch(() => []))
      setCameraErrorRevision((revision) => revision + 1)
      setCameraState({ status: 'error', message: recovery.message, recovery })
    }
  }, [logEvent, onDetected, screenContext, stopScanner, timeoutMs])

  startScannerRef.current = startScanner

  const startCompatibleCamera = useCallback(() => startScanner('', { compatibilityMode: true }), [startScanner])

  const scanImageFile = useCallback(async (file) => {
    if (!file) return false
    sessionIdRef.current = nextScannerSessionId()
    stopScanner(false, 'image-scan-start')
    setCameraState({ status: 'loading', message: 'Foto op barcode controleren…' })
    readerRef.current = readerRef.current || createBarcodeReader()
    const objectUrl = URL.createObjectURL(file)
    try {
      const result = await readerRef.current.decodeFromImageUrl(objectUrl)
      const detectedBarcode = String(result?.getText?.() || result?.text || '').trim()
      if (!detectedBarcode) throw new Error('Geen barcode gevonden in de foto')
      logEvent('IMAGE_DECODE_RESULT_FOUND', { text: detectedBarcode })
      setCameraState({ status: 'found', message: 'Barcode herkend.' })
      await onDetected?.(detectedBarcode, { logEvent, sessionId: sessionIdRef.current, screenContext })
      return true
    } catch (error) {
      logEvent('IMAGE_DECODE_ERROR', { errorName: error?.name, errorMessage: error?.message })
      setCameraErrorRevision((revision) => revision + 1)
      setCameraState({ status: 'error', message: 'Geen barcode in de foto herkend. Tik op Scannen om opnieuw te proberen of vul de barcode handmatig in.' })
      return false
    } finally {
      URL.revokeObjectURL(objectUrl)
    }
  }, [logEvent, onDetected, screenContext, stopScanner])

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
    cameraErrorRevision,
    cameraMeta,
    availableCameras,
    startScanner,
    startCompatibleCamera,
    stopScanner,
    switchCamera,
    scanImageFile,
  }
}
