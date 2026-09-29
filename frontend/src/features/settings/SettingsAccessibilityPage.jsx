import { useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import {
  FONT_SCALE_OPTIONS,
  readFontScalePreference,
  resetFontScalePreference,
  writeFontScalePreference,
} from '../../ui/fontScalePreference.js'

export default function SettingsAccessibilityPage() {
  const [fontScale, setFontScale] = useState(() => readFontScalePreference())

  function apply(value) {
    setFontScale(writeFontScalePreference(value))
  }

  function restore() {
    setFontScale(resetFontScalePreference())
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: 20 }} data-testid="settings-accessibility-page">
          <div>
            <h2 style={{ margin: '0 0 8px 0' }}>Toegankelijkheid</h2>
            <p style={{ margin: 0, color: '#667085' }}>
              Deze persoonlijke instelling is beschikbaar voor iedere ingelogde gebruiker en geldt op dit apparaat.
            </p>
          </div>
          <section style={{ display: 'grid', gap: 12 }} aria-labelledby="accessibility-text-size">
            <div>
              <h3 id="accessibility-text-size" style={{ margin: '0 0 4px 0' }}>Tekstgrootte</h3>
              <p style={{ margin: 0, color: '#667085' }}>
                Vergroot de tekst in heel InHuis. Browser- en systeemzoom blijven daarnaast beschikbaar.
              </p>
            </div>
            <div className="rz-settings-display-controls" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {Object.entries(FONT_SCALE_OPTIONS).map(([key, option]) => (
                <Button key={key} type="button" variant={fontScale === key ? 'primary' : 'secondary'} onClick={() => apply(key)}
                  aria-pressed={fontScale === key} data-testid={`settings-font-scale-${key}`}>
                  {option.label}
                </Button>
              ))}
              <Button type="button" variant="secondary" onClick={restore} data-testid="settings-font-scale-reset">Standaard herstellen</Button>
            </div>
          </section>
        </div>
      </Card>
    </AppShell>
  )
}
