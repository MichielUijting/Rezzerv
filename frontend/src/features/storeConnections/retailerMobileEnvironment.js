// Same-origin scripts must be installed and run explicitly in a supported browser.
// The user agent is guidance only; it is never evidence of a connected account.
export function detectMobileRetailerEnvironment(agent = (typeof navigator !== 'undefined' ? navigator : {})) {
  const ua = String(agent?.userAgent || '')
  const ios = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && Number(agent?.maxTouchPoints || 0) > 1)
  const android = !ios && /Android/i.test(ua)
  if (ios) return { device: 'iphone', browser: /Safari/i.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS/i.test(ua) ? 'safari' : 'other' }
  if (android) return { device: 'android', browser: /Chrome\/\d+/i.test(ua) && !/EdgA|OPR|SamsungBrowser|Firefox|\bwv\b|Version\/4\.0/i.test(ua) ? 'chrome' : 'other' }
  return { device: 'desktop', browser: 'desktop' }
}

// Explicit Android browser targeting avoids the installed PWA's same-origin
// link capture. Never put session data in the handoff or trust it as proof.
export function retailerBrowserHandoff(browserUrl, device, origin) {
  try {
    const url = new URL(browserUrl)
    if (url.origin !== origin || !['http:', 'https:'].includes(url.protocol) ||
        url.username || url.password) return null
    if (device !== 'android') return null
    return 'intent://' + url.host + url.pathname + url.search +
      '#Intent;scheme=' + url.protocol.slice(0, -1) +
      ';package=com.android.chrome;end'
  } catch {
    return null
  }
}
