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
