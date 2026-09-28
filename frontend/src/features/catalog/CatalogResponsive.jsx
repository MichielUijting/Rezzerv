import { useMobileAppViewport } from '../../app/mobileViewport.js'
import CatalogPage from './CatalogPage.jsx'
import MobileCatalogPage from './MobileCatalogPage.jsx'

export default function CatalogResponsive() {
  const isMobileViewport = useMobileAppViewport()
  return isMobileViewport ? <MobileCatalogPage /> : <CatalogPage />
}
