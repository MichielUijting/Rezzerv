import "./ui/tokens.css";
import "./ui/base.css";
import "./ui/components/button.css";
import "./ui/components/card.css";
import "./ui/components/header.css";
import "./ui/components/table.css";
import "./styles.css";

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import AdminArchiveCleanupButton from './features/admin/AdminArchiveCleanupButton.jsx'

function Root() {
  const isAdmin = typeof window !== 'undefined' && window.location.pathname === '/admin'
  return (
    <React.StrictMode>
      <App />
      {isAdmin ? <AdminArchiveCleanupButton /> : null}
    </React.StrictMode>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(<Root />)

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}
