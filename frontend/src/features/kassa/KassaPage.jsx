import { useMobileAppViewport } from '../../app/mobileViewport.js'
import DesktopKassaPage from '../receipts/KassaPage.jsx'
import MobileKassa from './MobileKassa.jsx'

export default function KassaPage() {
  return useMobileAppViewport() ? <MobileKassa /> : <DesktopKassaPage />
}
