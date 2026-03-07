import React from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import AdminPage from '../../features/admin/AdminPage'
import ArticlePage from '../../features/articles/ArticlePage'
import LoginPage from '../../features/auth/LoginPage'
import HomePage from '../../features/home/HomePage'
import SettingsPage from '../../features/settings/SettingsPage'
import SettingsArticleFieldsPage from '../../features/settings/SettingsArticleFieldsPage'
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

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route path="/reset-session" element={<ResetSessionRoute />} />
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/home" element={<Protected><HomePage /></Protected>} />
        <Route path="/voorraad" element={<Protected><Voorraad /></Protected>} />
        <Route path="/voorraad/:articleId" element={<Protected><ArticlePage /></Protected>} />
        <Route path="/instellingen" element={<Protected><SettingsPage /></Protected>} />
        <Route path="/instellingen/artikeldetails/veldzichtbaarheid" element={<Protected><SettingsArticleFieldsPage /></Protected>} />
        <Route path="/admin" element={<Protected><AdminPage /></Protected>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
