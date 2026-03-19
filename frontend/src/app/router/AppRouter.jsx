import React from 'react'
import { Navigate, RouterProvider, createBrowserRouter, useNavigate } from 'react-router-dom'
import AdminPage from '../../features/admin/AdminPage'
import ArticlePage from '../../features/articles/ArticlePage'
import LoginPage from '../../features/auth/LoginPage'
import HomePage from '../../features/home/HomePage'
import StoresPage from '../../features/stores/StoresPage'
import ReceiptsPage from '../../features/stores/ReceiptsPage'
import StoreBatchDetailPage from '../../features/stores/StoreBatchDetailPage'
import SettingsPage from '../../features/settings/SettingsPage'
import SettingsArticleFieldsPage from '../../features/settings/SettingsArticleFieldsPage'
import SettingsHouseholdAutomationPage from '../../features/settings/SettingsHouseholdAutomationPage'
import SettingsStoreImportPage from '../../features/settings/SettingsStoreImportPage'
import Voorraad from '../../pages/Voorraad'
import AuthGuard from './AuthGuard'

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

const router = createBrowserRouter([
  { path: '/login', element: <LoginRoute /> },
  { path: '/reset-session', element: <ResetSessionRoute /> },
  { path: '/', element: <Navigate to="/login" replace /> },
  { path: '/home', element: <Protected><HomePage /></Protected> },
  { path: '/voorraad', element: <Protected><Voorraad /></Protected> },
  { path: '/winkels', element: <Protected><StoresPage /></Protected> },
  { path: '/kassabonnen', element: <Protected><ReceiptsPage /></Protected> },
  { path: '/kassabon', element: <Protected><Navigate to="/import-kassabon" replace /></Protected> },
  { path: '/import-kassabon', element: <Protected><StoresPage /></Protected> },
  { path: '/winkels/batch/:batchId', element: <Protected><StoreBatchDetailPage /></Protected> },
  { path: '/voorraad/:articleId', element: <Protected><ArticlePage /></Protected> },
  { path: '/instellingen', element: <Protected><SettingsPage /></Protected> },
  { path: '/instellingen/artikeldetails/veldzichtbaarheid', element: <Protected><SettingsArticleFieldsPage /></Protected> },
  { path: '/instellingen/huishoudautomatisering', element: <Protected><SettingsHouseholdAutomationPage /></Protected> },
  { path: '/instellingen/winkelimport', element: <Protected><SettingsStoreImportPage /></Protected> },
  { path: '/admin', element: <Protected><AdminPage /></Protected> },
  { path: '*', element: <Navigate to="/login" replace /> },
])

export default function AppRouter() {
  return <RouterProvider router={router} />
}
