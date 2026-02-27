import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Input from '../../ui/Input.jsx'
import Button from '../../ui/Button.jsx'
import BrandLogo from '../../ui/BrandLogo.jsx'
import { apiPost } from '../../lib/apiClient.js'
import { useState } from 'react'

export default function LoginPage({ onLoggedIn }) {
  const [email, setEmail] = useState('admin@rezzerv.local')
  const [password, setPassword] = useState('Rezzerv123')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await apiPost('/api/auth/login', { email, password })
      if (!res.ok) throw new Error('Inloggen mislukt')
      const data = await res.json()
      onLoggedIn(data.token)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rz-screen">
      <Header title="Inloggen" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card>
            <div className="rz-logo-login">
              <BrandLogo variant="login" />
            </div>

            <form className="rz-form" onSubmit={onSubmit}>
              <Input
                label="E-mail"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@rezzerv.local"
              />
              <Input
                label="Wachtwoord"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Rezzerv123"
              />

              <Button type="submit" variant="primary"  disabled={loading} className="rz-btn-center">
                {loading ? 'Bezig...' : 'Inloggen'}
              </Button>

              {error && <div className="rz-alert">{error}</div>}
            </form>
          </Card>
        </div>
      </div>
</div>
  )
}
