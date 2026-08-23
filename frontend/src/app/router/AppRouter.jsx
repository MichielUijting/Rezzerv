import React from 'react'
import { Navigate, RouterProvider, createBrowserRouter, useNavigate, useParams } from 'react-router-dom'
import AdminPage from '../../features/admin/AdminPage'
import ArticlePage from '../../features/articles/ArticlePage'
import LoginPage from '../../features/auth/LoginPage'
import RegisterPage from '../../features/auth/RegisterPage'
import HomePage from '../../features/home/HomePage'
import OnboardingPage from '../../features/onboarding/OnboardingPage.jsx'
import ReceiptsPage from '../../features/receipts/ReceiptsPage'
import KassaPage from '../../features/kassa/KassaPage.jsx'
import SettingsPage from '../../features/settings/SettingsPage'
import SettingsCapabilitiesPage from '../../features/settings/SettingsCapabilitiesPage.jsx'
import SettingsArticleFieldsPage from '../../features/settings/SettingsArticleFieldsPage'
import SettingsArticleGroupsPage from '../../features/settings/SettingsArticleGroupsPage'
import SettingsHouseholdAutomationPage from '../../features/settings/SettingsHouseholdAutomationPage'
import SettingsAlmostOutPage from '../../features/settings/SettingsAlmostOutPage'
import SettingsStoreImportPage from '../../features/settings/SettingsStoreImportPage'
import SettingsHouseholdPage from '../../features/settings/SettingsHouseholdPage'
import SettingsAuthorizationPage from '../../features/settings/SettingsAuthorizationPage.jsx'
import SettingsLocationsRoutePage from '../../features/settings/SettingsLocationsRoutePage.jsx'
import SettingsPrivacyDataSharingPage from '../../features/settings/SettingsPrivacyDataSharingPage'
import Voorraad from '../../pages/Voorraad'
import ScannerLabPage from '../../pages/ScannerLabPage.jsx'
import ReceiptReviewPreviewPage from '../../pages/ReceiptReviewPreviewPage.jsx'
import IncidentalPurchasePage from '../../features/purchaseImport/IncidentalPurchasePage.jsx'
import AlmostOutPage from '../../features/almostOut/AlmostOutPage.jsx'
import ExternalDatabasesPage from '../../features/externalDatabases/ExternalDatabasesPage.jsx'
import ProductGroupsPage from '../../features/productGroups/ProductGroupsPage.jsx'
import LoyaltyStampsPage from '../../features/loyaltyStamps/LoyaltyStampsPage.jsx'
import CatalogPage from '../../features/catalog/CatalogPage.jsx'
import CatalogDetailPageV2 from '../../features/catalog/CatalogDetailPageV2.jsx'
import CatalogGpcActionPage from '../../features/catalog/CatalogGpcActionPage.jsx'
import HouseholdSupportPage from '../../features/support/HouseholdSupportPage.jsx'
import PlatformSupportPage from '../../features/support/PlatformSupportPage.jsx'
import ShoppingPage from '../../features/shopping/ShoppingPage.jsx'
import SuperuserDashboardPage from '../../features/superuser/SuperuserDashboardPage.jsx'
import { clearAuthSession } from '../../lib/authSession.js'
import AuthGuard from './AuthGuard'
import AdminGuard from './AdminGuard'
import FrontteamGuard from './FrontteamGuard'
import PermissionGuard from './PermissionGuard'
import SettingsGuard from './SettingsGuard'
import SuperuserGuard from './SuperuserGuard.jsx'

function LoginRoute() {
  const navigate = useNavigate()
  function handleLogin() {
    navigate('/home', { replace: false })
  }
  return <LoginPage onLoggedIn={handleLogin} />
}

function RegisterRoute() {
  const navigate = useNavigate()
  function handleRegistered() {
    navigate('/home', { replace: true })
  }
  return <RegisterPage onRegistered={handleRegistered} />
}

function OnboardingRoute() {
  const navigate = useNavigate()
  function handleUseCaseSelected() {
    navigate('/home', { replace: true })
  }
  return <OnboardingPage onUseCaseSelected={handleUseCaseSelected} />
}

function ResetSessionRoute() {
  React.useEffect(() => {
    clearAuthSession()
    window.location.replace('/login')
  }, [])
  return null
}

function LegacyReceiptBatchRouteRedirect() {
  const { batchId = '' } = useParams()
  const target = batchId ? `/kassabonnen?batch=${encodeURIComponent(batchId)}` : '/kassabonnen'
  return <Navigate to={target} replace />
}

function LegacyReceiptLineRouteRedirect() {
  const { batchId = '' } = useParams()
  const target = batchId ? `/kassabonnen?batch=${encodeURIComponent(batchId)}` : '/kassabonnen'
  return <Navigate to={target} replace />
}

function Protected({ children }) {
  return <AuthGuard>{children}</AuthGuard>
}

function ProtectedAdmin({ children }) {
  return <AuthGuard><AdminGuard>{children}</AdminGuard></AuthGuard>
}

function ProtectedFrontteam({ children }) {
  return <AuthGuard><FrontteamGuard>{children}</FrontteamGuard></AuthGuard>
}

function ProtectedPermission({ permission, children, message }) {
  return <AuthGuard><PermissionGuard permission={permission} message={message}>{children}</PermissionGuard></AuthGuard>
}

function ProtectedSettings({ children, allowViewer = true }) {
  return <AuthGuard><SettingsGuard allowViewer={allowViewer}>{children}</SettingsGuard></AuthGuard>
}

function ProtectedSuperuser({ children }) {
  return <AuthGuard><SuperuserGuard>{children}</SuperuserGuard></AuthGuard>
}

const router = createBrowserRouter([
  { path: '/login', element: <LoginRoute /> },
  { path: '/registreren', element: <RegisterRoute /> },
  { path: '/reset-session', element: <ResetSessionRoute /> },
  { path: '/', element: <Navigate to="/login" replace /> },
  { path: '/onboarding', element: <Protected><OnboardingRoute /></Protected> },
  { path: '/home', element: <Protected><HomePage /></Protected> },
  { path: '/meldingen', element: <Protected><HouseholdSupportPage /></Protected> },
  { path: '/superuser', element: <ProtectedSuperuser><SuperuserDashboardPage /></ProtectedSuperuser> },
  { path: '/superuser/meldingen', element: <ProtectedPermission permission="platform.support_access.read" message="Alleen de superuser kan alle meldingen bekijken."><PlatformSupportPage /></ProtectedPermission> },
  { path: '/voorraad', element: <Protected><Voorraad /></Protected> },
  { path: '/bijna-op', element: <Protected><AlmostOutPage /></Protected> },
  { path: '/winkelen', element: <ProtectedPermission permission="shopping_list.view" message="Je rol mag Winkelen niet bekijken."><ShoppingPage /></ProtectedPermission> },
  { path: '/spaartegoeden', element: <Protected><LoyaltyStampsPage /></Protected> },
  { path: '/productgroepen', element: <Protected><ProductGroupsPage /></Protected> },
  { path: '/voorraad/incidentele-aankoop', element: <Protected><IncidentalPurchasePage /></Protected> },
  { path: '/dev/scanner-lab', element: <Protected><ScannerLabPage /></Protected> },
  { path: '/dev/receipt-review-preview', element: <Protected><ReceiptReviewPreviewPage /></Protected> },
  { path: '/kassabonnen', element: <Protected><ReceiptsPage /></Protected> },
  { path: '/kassa', element: <Protected><KassaPage /></Protected> },
  { path: '/kassa/nieuw', element: <Protected><KassaPage /></Protected> },
  { path: '/externe-databases', element: <ProtectedFrontteam><ExternalDatabasesPage /></ProtectedFrontteam> },
  { path: '/catalogus', element: <Protected><CatalogPage /></Protected> },
  { path: '/catalogus/gpc-classificeren', element: <ProtectedPermission permission="gpc.update" message="Je rol mag GPC bekijken, maar niet wijzigen."><CatalogGpcActionPage /></ProtectedPermission> },
  { path: '/catalogus/:globalProductId', element: <Protected><CatalogDetailPageV2 /></Protected> },
  { path: '/kassabon', element: <Protected><Navigate to="/kassa" replace /></Protected> },
  { path: '/import-kassabon', element: <Protected><Navigate to="/kassabonnen" replace /></Protected> },
  { path: '/kassabonnen/batch/:batchId', element: <Protected><LegacyReceiptBatchRouteRedirect /></Protected> },
  { path: '/kassabonnen/batch/:batchId/regel/:receiptLineId', element: <Protected><LegacyReceiptLineRouteRedirect /></Protected> },
  { path: '/voorraad/:articleId', element: <Protected><ArticlePage /></Protected> },
  { path: '/instellingen', element: <ProtectedSettings allowViewer={true}><SettingsPage /></ProtectedSettings> },
  { path: '/instellingen/mogelijkheden', element: <ProtectedPermission permission="household_settings.manage" message="Alleen de beheerder kan de mogelijkheden van het huishouden uitbreiden."><SettingsCapabilitiesPage /></ProtectedPermission> },
  { path: '/instellingen/artikeldetails/veldzichtbaarheid', element: <ProtectedSettings allowViewer={true}><SettingsArticleFieldsPage /></ProtectedSettings> },
  { path: '/instellingen/artikelgroepen', element: <ProtectedSettings allowViewer={false}><SettingsArticleGroupsPage /></ProtectedSettings> },
  { path: '/instellingen/privacy-datadeling', element: <ProtectedSettings allowViewer={true}><SettingsPrivacyDataSharingPage /></ProtectedSettings> },
  { path: '/instellingen/huishoudautomatisering', element: <ProtectedSettings allowViewer={false}><SettingsHouseholdAutomationPage /></ProtectedSettings> },
  { path: '/instellingen/bijna-op-voorspelling', element: <ProtectedSettings allowViewer={false}><SettingsAlmostOutPage /></ProtectedSettings> },
  { path: '/instellingen/winkelimport', element: <ProtectedSettings allowViewer={false}><SettingsStoreImportPage /></ProtectedSettings> },
  { path: '/instellingen/huishouden', element: <ProtectedSettings allowViewer={false}><SettingsHouseholdPage /></ProtectedSettings> },
  { path: '/instellingen/huishouden/autorisaties', element: <ProtectedSettings allowViewer={true}><SettingsAuthorizationPage /></ProtectedSettings> },
  { path: '/instellingen/locaties', element: <ProtectedSettings allowViewer={false}><SettingsLocationsRoutePage /></ProtectedSettings> },
  { path: '/instellingen/ruimtes', element: <ProtectedSettings allowViewer={false}><Navigate to="/instellingen/locaties" replace /></ProtectedSettings> },
  { path: '/instellingen/sublocaties', element: <ProtectedSettings allowViewer={false}><Navigate to="/instellingen/locaties" replace /></ProtectedSettings> },
  { path: '/admin', element: <ProtectedAdmin><AdminPage /></ProtectedAdmin> },
  { path: '*', element: <Navigate to="/login" replace /> },
])

export default function AppRouter() {
  return <RouterProvider router={router} />
}
