import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import { getRezzervVersionTag } from '../../ui/version.js'

function InfoRow({ title, description, to, linkLabel, testId }) {
  return (
    <section style={{ display: 'grid', gap: '8px' }} aria-labelledby={`${testId}-title`}>
      <div>
        <h3 id={`${testId}-title`} style={{ margin: '0 0 4px 0', fontSize: '17px' }}>{title}</h3>
        <p style={{ margin: 0, color: '#667085', fontSize: '14px' }}>{description}</p>
      </div>
      {to ? (
        <div>
          <Link to={to} data-testid={testId} style={{ fontWeight: 600 }}>
            {linkLabel}
          </Link>
        </div>
      ) : null}
    </section>
  )
}

export default function SettingsHelpAboutPage() {
  const [version, setVersion] = useState(getRezzervVersionTag())

  useEffect(() => {
    const refreshVersion = () => setVersion(getRezzervVersionTag())
    window.addEventListener('rezzerv-version-ready', refreshVersion)
    return () => window.removeEventListener('rezzerv-version-ready', refreshVersion)
  }, [])

  return (
    <AppShell title="Instellingen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: '20px' }} data-testid="settings-help-about-page">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
            <div>
              <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Hulp & Over</h2>
              <p style={{ margin: 0, color: '#667085' }}>Ondersteuning en informatie over Inhuis.</p>
            </div>
          </div>

          <section style={{ display: 'grid', gap: '8px' }} aria-labelledby="help-about-version-title">
            <div>
              <h3 id="help-about-version-title" style={{ margin: '0 0 4px 0', fontSize: '17px' }}>Over Inhuis</h3>
              <p style={{ margin: 0, color: '#667085', fontSize: '14px' }}>Actuele applicatieversie.</p>
            </div>
            <div data-testid="help-about-version" style={{ fontWeight: 600 }}>
              Versie {version}
            </div>
          </section>

          <InfoRow
            title="Hulp & contact"
            description="Bekijk meldingen en neem via de bestaande ondersteuningsflow contact op."
            to="/meldingen"
            linkLabel="Naar meldingen en ondersteuning"
            testId="help-about-support-link"
          />

          <InfoRow
            title="Privacy & datadeling"
            description="Bekijk en beheer je persoonlijke toestemming voor privacy en datadeling."
            to="/instellingen/privacy-datadeling"
            linkLabel="Naar Privacy & Datadeling"
            testId="help-about-privacy-link"
          />
        </div>
      </Card>
    </AppShell>
  )
}
