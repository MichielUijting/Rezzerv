import ShoppingPage from './ShoppingPage.jsx'
import MobileShopping from './MobileShopping.jsx'
import { useMobileAppViewport } from '../../app/mobileViewport.js'

export default function ShoppingResponsive() {
  const isMobileViewport = useMobileAppViewport()

  if (isMobileViewport) {
    return <MobileShopping />
  }

  return <ShoppingPage />
}
