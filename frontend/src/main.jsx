import "./ui/tokens.css";
import "./ui/base.css";
import "./ui/components/button.css";
import "./ui/components/card.css";
import "./ui/components/header.css";
import "./ui/components/table.css";

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)