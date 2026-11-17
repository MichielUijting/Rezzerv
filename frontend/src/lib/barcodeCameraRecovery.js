/** Browser-safe camera recovery. Never change OS or browser privacy settings.
 * A getUserMedia request may prompt the user. Any track constraints applied
 * during the scan disappear when its MediaStreamTracks are stopped.
 */
export function diagnoseBarcodeCameraFailure(error, {
  secureContext = true,
  mediaSupported = true,
  userAgent = '',
} = {}) {
  const name = String(error?.name || '').toLowerCase()
  const detail = String(error?.message || error || '').toLowerCase()
  const firefox = /firefox/i.test(userAgent)
  const windows = /windows/i.test(userAgent)

  if (!mediaSupported && secureContext) {
    return {
      reason: 'unsupported_browser',
      message: 'Deze browser biedt geen live cameratoegang.',
      advice: 'Probeer een actuele browser met cameratoegang of kies Barcode uit foto. Inhuis verandert geen apparaatinstellingen.',
      canTryCompatibility: false,
    }
  }
  if (!secureContext || name === 'securityerror' || detail.includes('insecure context')) {
    return {
      reason: 'insecure_or_unsupported',
      message: 'De camera kan hier niet veilig worden gebruikt.',
      advice: 'Open Inhuis via HTTPS of op localhost. Op een onbeveiligd netwerkadres kan de browser geen cameratoestemming vragen.',
      canTryCompatibility: false,
    }
  }
  if (name === 'notallowederror' || name === 'permissiondeniederror' ||
      detail.includes('permission denied') || detail.includes('permission dismissed')) {
    return {
      reason: 'permission',
      message: 'De browser of het apparaat blokkeert cameratoegang voor Inhuis.',
      advice: firefox
        ? 'Controleer het camera-/toestemmingsicoon links in de Firefox-adresbalk, verwijder een eventuele blokkering en kies Toestaan bij een nieuwe aanvraag.'
        : 'Controleer de cameratoestemming van deze website in de adresbalk en kies Toestaan bij een nieuwe aanvraag.',
      deviceAdvice: windows
        ? 'Op Windows: Instellingen → Privacy en beveiliging → Camera. Controleer Cameratoegang en Toegang voor bureaublad-apps. Inhuis kan deze instellingen niet zelf wijzigen.'
        : 'Controleer zo nodig de cameratoestemming voor de browser in de apparaatinstellingen.',
      canTryCompatibility: false,
    }
  }
  if (name === 'notfounderror' || detail.includes('requested device not found') ||
      detail.includes('devices not found')) {
    return {
      reason: 'no_device',
      message: 'Er is geen beschikbare camera gevonden.',
      advice: 'Controleer of de laptopcamera of aangesloten webcam aanwezig en ingeschakeld is. Sluit zo nodig een webcam aan en probeer opnieuw.',
      canTryCompatibility: false,
    }
  }
  if (name === 'notreadableerror' || name === 'trackstarterror' ||
      name === 'aborterror' || detail.includes('failed to allocate videosource') ||
      detail.includes('could not start video source') || detail.includes('device in use')) {
    return {
      reason: 'busy_or_unavailable',
      message: 'De camera is bezet of kon met de huidige instellingen niet starten.',
      advice: 'Sluit andere apps of browsertabbladen die de camera gebruiken. Je kunt Inhuis ook expliciet met een tijdelijke eenvoudige camera-instelling laten proberen.',
      canTryCompatibility: true,
    }
  }
  if (name === 'overconstrainederror' || detail.includes('constraint')) {
    return {
      reason: 'constraints',
      message: 'De gekozen video-instellingen worden niet ondersteund.',
      advice: 'Probeer een tijdelijke eenvoudige camera-instelling zonder vaste camera, beeldresolutie of scherpstelinstellingen.',
      canTryCompatibility: true,
    }
  }
  return {
    reason: 'unknown',
    message: 'De camera kon niet worden gestart.',
    advice: 'Probeer een andere aangesloten camera of kies Barcode uit foto. Inhuis kan ook een tijdelijke eenvoudige camera-instelling proberen.',
    canTryCompatibility: true,
  }
}

export function shouldStopCameraRetries(error) {
  const name = String(error?.name || '').toLowerCase()
  return ['notallowederror', 'permissiondeniederror', 'permissiondismissederror', 'securityerror'].includes(name)
    || String(error?.message || '').toLowerCase().includes('permission denied')
}
