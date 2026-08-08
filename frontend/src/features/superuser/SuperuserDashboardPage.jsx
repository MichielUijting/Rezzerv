import { useEffect, useState } from 'react'
import Header from '../../ui/Header.jsx'
import ScreenCard from '../../ui/ScreenCard.jsx'
import Tabs from '../../ui/Tabs.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

const TABS = ['Overzicht', 'Huishoudens', 'Gebruik', 'Kassabonnen', 'Systeem']

function EmptySection({ title }) {
  return (
    <section aria-label={title}>
      <h2 style={{ marginTop: 0, fontSize: 20 }}>{title}</h2>
      <p style={{ marginBottom: 0 }}>
        Dit onderdeel wordt in een volgende Superuser-release gevuld. S1 levert uitsluitend het veilige beheerfundament.
      </p>
    </section>
  )
}

export default function SuperuserDashboardPage() {
  const [access, setAccess] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      try {
        const response = await fetchJsonWithAuth('/api/superuser/bootstrap')
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload?.detail || 'Superuser-toegang kon niet worden gevalideerd.')
        if (cancelled) return
        setAccess(payload)
        await fetchJsonWithAuth('/api/superuser/audit/open', { method: 'POST' })
      } catch (nextError) {
        if (!cancelled) setError(String(nextError?.message || nextError || 'Superuser-toegang mislukt.'))
      }
    }
    bootstrap()
    return () => { cancelled = true }
  }, [])

  return (
    <div className="rz-screen" data-testid="superuser-dashboard">
      <Header title="Rezzerv Beheercentrum" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <ScreenCard fullWidth>
            {error ? (
              <div role="alert">{error}</div>
            ) : !access ? (
              <div role="status">Superuser-toegang wordt gecontroleerd…</div>
            ) : (
              <>
                <div
                  role="status"
                  aria-label="Superuser alleen-lezen status"
                  style={{
                    marginBottom: 16,
                    padding: '10px 12px',
                    border: '1px solid #d4ddd4',
                    borderRadius: 6,
                    background: '#f7faf7',
                  }}
                >
                  <strong>Superuser</strong> — beheercentrum. Toegang: <strong>alleen lezen</strong>.
                </div>
                <Tabs tabs={Array.isArray(access.tabs) ? access.tabs : TABS} defaultTab="Overzicht">
                  {(activeTab) => <EmptySection title={activeTab} />}
                </Tabs>
              </>
            )}
          </ScreenCard>
        </div>
      </div>
    </div>
  )
}
