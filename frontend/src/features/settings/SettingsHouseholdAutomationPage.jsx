import { useEffect, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import {
  getHouseholdAutomationSettings,
  saveHouseholdAutomationSettings,
} from './services/householdAutomationService'

export default function SettingsHouseholdAutomationPage() {
  const [autoConsumeOnRepurchase, setAutoConsumeOnRepurchase] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')

  useEffect(() => {
    const settings = getHouseholdAutomationSettings()
    setAutoConsumeOnRepurchase(Boolean(settings.autoConsumeOnRepurchase))
  }, [])

  function handleSave() {
    saveHouseholdAutomationSettings({ autoConsumeOnRepurchase })
    setSaveMessage('Instelling opgeslagen')
    window.setTimeout(() => setSaveMessage(''), 2500)
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: '18px' }}>
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Huishoudautomatisering</h2>
            <p style={{ margin: 0, color: '#667085' }}>
              Deze instelling geldt voor het hele huishouden. Wanneer de instelling aan staat, kan Rezzerv bij een herhaalaankoop van een verbruiksartikel automatisch een verbruikevent toevoegen.
            </p>
          </div>

          <div className="rz-automation-setting-card">
            <div className="rz-automation-setting-copy">
              <div className="rz-automation-setting-title">Slim afboeken bij herhaalaankoop</div>
              <div className="rz-automation-setting-text">Alleen voor verbruiksartikelen. Automatische afboekingen worden zichtbaar vastgelegd in Historie.</div>
            </div>
            <label className="rz-toggle-row">
              <span className="sr-only">Slim afboeken bij herhaalaankoop</span>
              <input
                type="checkbox"
                checked={autoConsumeOnRepurchase}
                onChange={(event) => {
                  setSaveMessage('')
                  setAutoConsumeOnRepurchase(event.target.checked)
                }}
                className="rz-toggle-row-input"
              />
            </label>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            {saveMessage ? <div className="rz-inline-feedback rz-inline-feedback--success">{saveMessage}</div> : <div />}
            <Button onClick={handleSave}>Opslaan</Button>
          </div>
        </div>
      </Card>
    </AppShell>
  )
}
