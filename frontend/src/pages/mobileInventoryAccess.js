// Backward-compatible aliases for older imports. UI variant selection is
// application-wide and viewport-only; user roles and permissions never decide
// whether a mobile or desktop presentation is rendered.
export {
  MOBILE_APP_MEDIA_QUERY as MOBILE_INVENTORY_MEDIA_QUERY,
  isMobileAppViewport as isMobileInventoryViewport,
  readMobileAppViewport,
  useMobileAppViewport,
} from '../app/mobileViewport.js'

export function isMobileInventoryEligibleContext() {
  return true
}
