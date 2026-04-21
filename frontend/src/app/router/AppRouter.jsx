import React from 'react'
import { Navigate, RouterProvider, createBrowserRouter, useNavigate } from 'react-router-dom'
import AdminPage from '../../features/admin/AdminPage'
import ArticlePage from '../../features/articles/ArticlePage'
import LoginPage from '../../features/auth/LoginPage'
import HomePage from '../../features/home/HomePage'
import ReceiptsPage from '../../features/stores/ReceiptsPage'
import KassaPage from '../../features/receipts/KassaPage'
import StoreBatchDetailPage from '../../features/stores/StoreBatchDetailPage'
import SettingsPage from '../../features/settings/SettingsPage'
import SettingsArticleFieldsPage from '../../features/settings/SettingsArticleFieldsPage'
import SettingsHouseholdAutomationPage from '../../features/settings/SettingsHouseholdAutomationPage'
import SettingsAlmostOutPage from '../../features/settings/SettingsAlmostOutPage'
import SettingsStoreImportPage from '../../features/settings/SettingsStoreImportPage'
import SettingsHouseholdPage from '../../features/settings/SettingsHouseholdPage'
import SettingsLocationsPage from '../../features/settings/SettingsLocationsPage'
import SettingsPrivacyDataSharingPage from '../../features/settings/SettingsPrivacyDataSharingPage'
import Voorraad from '../../pages/Voorraad'
import RegressionRunnerPage from '../../features/admin/RegressionRunnerPage'
import ScannerLabPage from '../../pages/ScannerLabPage.jsx'
import IncidentalPurchasePage from '../../pages/IncidentalPurchasePage.jsx'
import AlmostOutPage from '../../features/almostOut/AlmostOutPage.jsx'
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
  { path: '/regression-runner', element: <ProtectedAdmin><RegressionRunnerPage /></ProtectedAdmin> },
  { path: '/home', element: <Protected><HomePage /></Protected> },
  { path: '/voorraad', element: <Protected><Voorraad /></Protected> },
  { path: '/bijna-op', element: <Protected><AlmostOutPage /></Protected> },
  { path: '/voorraad/incidentele-aankoop', element: <Protected><IncidentalPurchasePage /></Protected> },
  { path: '/dev/scanner-lab', element: <Protected><ScannerLabPage /></Protected> },
  { path: '/kassabonnen', element: <Protected><ReceiptsPage /></Protected> },
  { path: '/kassa', element: <Protected><KassaPage /></Protected> },
  { path: '/kassa/nieuw', element: <Protected><KassaPage /></Protected> },
  { path: '/kassabon', element: <Protected><Navigate to="/kassa" replace /></Protected> },
  { path: '/import-kassabon', element: <Protected><Navigate to="/kassabonnen" replace /></Protected> },
  { path: '/kassabonnen/batch/:batchId', element: <Protected><StoreBatchDetailPage /></Protected> },
  { path: '/voorraad/:articleId', element: <Protected><ArticlePage /></Protected> },
  { path: '/instellingen', element: <ProtectedSettings allowViewer={true}><SettingsPage /></ProtectedSettings> },
  { path: '/instellingen/artikeldetails/veldzichtbaarheid', element: <ProtectedSettings allowViewer={true}><SettingsArticleFieldsPage /></ProtectedSettings> },
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
