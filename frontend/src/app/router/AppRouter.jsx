import React from 'react'
import { Navigate, RouterProvider, createBrowserRouter, useNavigate, useParams } from 'react-router-dom'
import AdminPage from '../../features/admin/AdminPage'
import ArticlePage from '../../features/articles/ArticlePage'
import ArticleGpcPage from '../../features/articles/ArticleGpcPage'
import ArticleGpcInlineSummary from '../../features/articles/components/ArticleGpcInlineSummary'
import LoginPage from '../../features/auth/LoginPage'
import HomePage from '../../features/home/HomePage'
import ReceiptsPage from '../../features/receipts/ReceiptsPage'
import KassaPage from '../../features/kassa/KassaPage.jsx'
import SettingsPage from '../../features/settings/SettingsPage'
import SettingsArticleFieldsPage from '../../features/settings/SettingsArticleFieldsPage'
import SettingsArticleGroupsPage from '../../features/settings/SettingsArticleGroupsPage'
import SettingsHouseholdAutomationPage from '../../features/settings/SettingsHouseholdAutomationPage'
import SettingsAlmostOutPage from '../../features/settings/SettingsAlmostOutPage'
import SettingsStoreImportPage from '../../features/settings/SettingsStoreImportPage'
import SettingsHouseholdPage from '../../features/settings/SettingsHouseholdPage'
import SettingsLocationsPage from '../../features/settings/SettingsLocationsPage'
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
import CatalogDetailPage from '../../features/catalog/CatalogDetailPage.jsx'
import AuthGuard from './AuthGuard'
import AdminGuard from './AdminGuard'
import SettingsGuard from './SettingsGuard'

function LoginRoute() {
  const navigate = useNavigate()
  function handleLogin(newToken, email) {
    localStorage.setItem('rezzerv_token', newToken)
    if (email) localStorage.setItem('rezzerv_user_email', email)
    navigate('/home', { replace: false })
  }
  return <LoginPage onLoggedIn={handleLogin} />
}

function ResetSessionRoute() {
  React.useEffect(() => {
    try {
      localStorage.removeItem('rezzerv_token')
      localStorage.removeItem('rezzerv_user_email')
      sessionStorage.clear()
    } finally {
      window.location.replace('/login')
    }
  }, [])
  return null
}

function LegacyReceiptBatchRouteRedirect() {
  const { batchId = '' } = useParams()
  const target = batchId
    ? `/kassabonnen?batch=${encodeURIComponent(batchId)}`
    : '/kassabonnen'
  return <Navigate to={target} replace />
}

function LegacyReceiptLineRouteRedirect() {
  const { batchId = '' } = useParams()
  const target = batchId
    ? `/kassabonnen?batch=${encodeURIComponent(batchId)}`
    : '/kassabonnen'
  return <Navigate to={target} replace />
}

function ArticleRoute() {
  const { articleId = '' } = useParams()
  return (
    <>
      <ArticlePage />
      <ArticleGpcInlineSummary articleId={articleId} />
    </>
  )
}

function Protected({ children }) {
  return <AuthGuard>{children}</AuthGuard>
}

function ProtectedAdmin({ children }) {
  return <AuthGuard><AdminGuard>{children}</AdminGuard></AuthGuard>
}

function ProtectedSettings({ children, allowViewer = true }) {
  return <AuthGuard><SettingsGuard allowViewer={allowViewer}>{children}</SettingsGuard></AuthGuard>
}

const router = createBrowserRouter([
  { path: '/login', element: <LoginRoute /> },
  { path: '/reset-session', element: <ResetSessionRoute /> },
  { path: '/', element: <Navigate to="/login" replace /> },
  { path: '/home', element: <Protected><HomePage /></Protected> },
  { path: '/voorraad', element: <Protected><Voorraad /></Protected> },
  { path: '/bijna-op', element: <Protected><AlmostOutPage /></Protected> },
  { path: '/spaartegoeden', element: <Protected><LoyaltyStampsPage /></Protected> },
  { path: '/productgroepen', element: <Protected><ProductGroupsPage /></Protected> },
  { path: '/voorraad/incidentele-aankoop', element: <Protected><IncidentalPurchasePage /></Protected> },
  { path: '/dev/scanner-lab', element: <Protected><ScannerLabPage /></Protected> },
  { path: '/dev/receipt-review-preview', element: <Protected><ReceiptReviewPreviewPage /></Protected> },
  { path: '/kassabonnen', element: <Protected><ReceiptsPage /></Protected> },
  { path: '/kassa', element: <Protected><KassaPage /></Protected> },
  { path: '/kassa/nieuw', element: <Protected><KassaPage /></Protected> },
  { path: '/externe-databases', element: <Protected><ExternalDatabasesPage /></Protected> },
  { path: '/catalogus', element: <ProtectedAdmin><CatalogPage /></ProtectedAdmin> },
  { path: '/catalogus/:globalProductId', element: <ProtectedAdmin><CatalogDetailPage /></ProtectedAdmin> },
  { path: '/kassabon', element: <Protected><Navigate to="/kassa" replace /></Protected> },
  { path: '/import-kassabon', element: <Protected><Navigate to="/kassabonnen" replace /></Protected> },
  { path: '/kassabonnen/batch/:batchId', element: <Protected><LegacyReceiptBatchRouteRedirect /></Protected> },
  { path: '/kassabonnen/batch/:batchId/regel/:receiptLineId', element: <Protected><LegacyReceiptLineRouteRedirect /></Protected> },
  { path: '/voorraad/:articleId', element: <Protected><ArticleRoute /></Protected> },
  { path: '/voorraad/:articleId/gpc', element: <Protected><ArticleGpcPage /></Protected> },
  { path: '/instellingen', element: <ProtectedSettings allowViewer={true}><SettingsPage /></ProtectedSettings> },
  { path: '/instellingen/artikeldetails/veldzichtbaarheid', element: <ProtectedSettings allowViewer={true}><SettingsArticleFieldsPage /></ProtectedSettings> },
  { path: '/instellingen/artikelgroepen', element: <ProtectedSettings allowViewer={false}><SettingsArticleGroupsPage /></ProtectedSettings> },
  { path: '/instellingen/privacy-datadeling', element: <ProtectedSettings allowViewer={true}><SettingsPrivacyDataSharingPage /></ProtectedSettings> },
  { path: '/instellingen/huishoudautomatisering', element: <ProtectedSettings allowViewer={false}><SettingsHouseholdAutomationPage /></ProtectedSettings> },
  { path: '/instellingen/bijna-op-voorspelling', element: <ProtectedSettings allowViewer={false}><SettingsAlmostOutPage /></ProtectedSettings> },
  { path: '/instellingen/winkelimport', element: <ProtectedSettings allowViewer={false}><SettingsStoreImportPage /></ProtectedSettings> },
  { path: '/instellingen/huishouden', element: <ProtectedSettings allowViewer={false}><SettingsHouseholdPage /></ProtectedSettings> },
  { path: '/instellingen/locaties', element: <ProtectedSettings allowViewer={false}><SettingsLocationsPage /></ProtectedSettings> },
  { path: '/instellingen/ruimtes', element: <ProtectedSettings allowViewer={false}><Navigate to="/instellingen/locaties" replace /></ProtectedSettings> },
  { path: '/instellingen/sublocaties', element: <ProtectedSettings allowViewer={false}><Navigate to="/instellingen/locaties" replace /></ProtectedSettings> },
  { path: '/admin', element: <ProtectedAdmin><AdminPage /></ProtectedAdmin> },
  { path: '*', element: <Navigate to="/login" replace /> },
])

export default function AppRouter() {
  return <RouterProvider router={router} />
}
